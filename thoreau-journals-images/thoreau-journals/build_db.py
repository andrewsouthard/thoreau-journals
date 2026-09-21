#!/usr/bin/env python3
"""Universal Thoreau journal parser: all 14 Walden volumes -> SQLite + JSON.

Date model: Walden PDFs carry running page headers `[YEAR` / `[MONTH DAY`.
A `[MONTH DAY]` header DIFFERENT from the current entry's date starts a new
entry; a repeat of the current date (multi-page entry) is a continuation.
A `[YEAR`-only header sets year context and never splits. Year rollover
(Dec -> Jan) increments the year when no explicit year header intervenes.

Undated material (Vol I ch.8 mutilated journal, ch.9 commonplace-book,
front-matter before the first date header) is kept as dated=0 entries.
"""

import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
PDF_BASE = "https://www.walden.org/wp-content/uploads/2016/02"
PDF_DIR = BASE / "pdfs"
DB_PATH = BASE / "thoreau.db"
JSON_PATH = BASE / "thoreau.json"
VOLUME_MAP = BASE / "volume_map.tsv"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
# OCR confusions seen in the text layer (Z5 -> 25, Q5 -> 25, s -> 5)
OCR_DIGITS = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1",
                            "Z": "2", "z": "2", "A": "4", "S": "5",
                            "s": "5", "B": "8", "b": "6", "Q": "2", "g": "9"})

DATE_LINE = re.compile(
    r"""^\s*[\[\(]?\s*
    (?P<mon>January|February|March|April|May|June|July|August|
           September|October|November|December|
           Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b[\s.]*?
    (?P<day>['’]?\d{1,2}(?:st|nd|rd|th)?|['’]?[A-Za-z]+)?
    \s*[\.\)\]]?\s*(?:\.?\s*)?$""",
    re.IGNORECASE | re.VERBOSE)
YEAR_ONLY = re.compile(r"^\s*[\[\(]?\s*(?P<y>18[3-6][0-9])1?[\]\)\.]?\s*$")
YEAR_RANGE = re.compile(r"^\s*[\[\(]?\s*(?P<y1>18[3-6][0-9])\s*[-–]\s*(?P<y2>\d{2,4})\s*\]?\s*$")
NUMBER_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25,
    "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28,
    "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
    # roman numerals (Thoreau: "MARCH I" = March 1)
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}
RUNNING_JUNK = re.compile(
    r"^\s*(JOURNAL\.?|VOLUME\s+[IVXL]+|[IVXL]{1,5}|[A-Z]\s*\.?\s*)+\.?\s*$|^\s*\d{1,4}\s*$")


def parse_month_day(line):
    """Return (month, day) or (None, None). Day may be OCR-garbled."""
    m = DATE_LINE.match(line)
    if not m:
        return None, None
    mon = m.group("mon").upper()[:3]
    if mon not in MONTHS:
        return None, None
    month = MONTHS[mon]
    raw_day = (m.group("day") or "").strip().rstrip(".")
    if not raw_day:
        return month, None
    if re.fullmatch(r"[A-Za-z-]+", raw_day):
        # number-word ("May first") or roman numeral ("MARCH I")
        w = raw_day.lower()
        day = NUMBER_WORDS.get(w)
        if day is None:
            w2 = re.sub(r"(st|nd|rd|th)$", "", w)
            day = NUMBER_WORDS.get(w2)
        if day is None and len(raw_day) == 1:
            # single OCR-garbled digit ("[FEB . s")
            digits = re.sub(r"[^0-9]", "", raw_day.translate(OCR_DIGITS))
            if digits and digits.isdigit() and 1 <= int(digits) <= 31:
                day = int(digits)
        return month, day
    digits = re.sub(r"[^0-9]", "", raw_day)
    if re.search(r"[A-Za-z]", raw_day):
        # mixed token ("Z5", "Q5", "lfi") — OCR-garbled digits win
        fixed = re.sub(r"[^0-9]", "", raw_day.translate(OCR_DIGITS))
        if fixed and fixed.isdigit() and 1 <= int(fixed) <= 31:
            return month, int(fixed)
        return month, None
    if digits and digits.isdigit() and 1 <= int(digits) <= 31:
        return month, int(digits)
    return month, None  # month readable, day garbled


def looks_like_header(line):
    """Heuristic: line resembles a date/running header (for noise filtering)."""
    s = line.strip()
    if not s:
        return True
    if s.startswith("[") or s.startswith("("):
        return True
    if YEAR_ONLY.match(s) or YEAR_RANGE.match(s):
        return True
    if RUNNING_JUNK.match(s):
        return True
    if DATE_LINE.match(s):
        # month readable but day garbled: only treat as header noise if
        # short (a running-head repeat, not a "May our ..." sentence)
        mon, day = parse_month_day(s)
        if mon is not None and day is None and len(s) < 20:
            return True
        if mon is not None and day is not None:
            return True
    return False


MONTH_TITLE = re.compile(
    r"^\s*(?P<name>[A-Za-z'’\.0-9:]{3,14})\s*[,\.]*\s*(?P<y>18[3-6][0-9])?\s*$")
LEAD_DATE = re.compile(
    r"""^\s*[\[\(']?\s*
    (?P<mon>January|February|March|April|May|June|July|August|
           September|October|November|December|
           Jan\.|Feb\.|Mar\.|Apr\.|May|Jun\.|Jul\.|Aug\.|Sept\.|
           Sep\.|Oct\.|Nov\.|Dec\.)\s*
    (?P<day>\d{1,2}|[A-Za-z]{2,})""",
    re.IGNORECASE | re.VERBOSE)
DAY_ONLY = re.compile(r"^\s*'?(?P<d>\d{1,2})(?:st|nd|rd|th)?\s*\.(?!\d).*$")
INLINE_YEAR = re.compile(r"(?P<mon>January|February|March|April|May|June|July|August|"
                         r"September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|"
                         r"Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b.*?,?\s*(?P<y>1[678][0-9][0-9])\b",
                         re.IGNORECASE)


def fuzzy_month(name):
    """Best-guess month from a (possibly OCR-garbled) title word."""
    import difflib
    clean = re.sub(r"[^A-Z]", "", name.upper())
    if not clean:
        return None
    if clean[:3] in MONTHS:
        return MONTHS[clean[:3]]
    if len(clean) < 4:
        return None  # too short to be a month name, likely prose
    match = difflib.get_close_matches(
        clean, ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER",
                "DECEMBER"], n=1, cutoff=0.85)
    full = {"JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5,
            "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
            "NOVEMBER": 11, "DECEMBER": 12}
    return full.get(match[0]) if match else None


def is_list_next(lines, idx):
    """Lookahead: is the next non-junk line list-like (not prose)?

    Genuine entry headers are followed by prose; phenology-table date
    lines ('April 30', 'May 4') are followed by more list fragments.
    """
    seen = 0
    for j in range(idx + 1, len(lines)):
        s, _ = lines[j]
        if not s or RUNNING_JUNK.match(s):
            continue
        if YEAR_ONLY.match(s) or YEAR_RANGE.match(s):
            continue
        seen += 1
        if seen > 3:
            return False  # prose resumes -> it was a header
        if DATE_LINE.match(s):
            return True  # another date line -> list
        if re.fullmatch(r"\d{1,2}[a-z]{0,3}\.?", s):
            return True  # bare day number -> list
        if len(s) >= 40:
            return False  # prose line -> header
    return False


def parse_volume(pdf_paths, start_year, end_year):
    """Parse one volume's PDFs in order. Returns list of entry dicts."""
    entries = []
    cur = None          # current dated entry under construction
    cur_lines = []
    pre_lines = []      # undated front-matter accumulator
    pre_page = 0
    pre_pdf = ""
    year = start_year
    prev_month = None
    clamped = 0
    retro = 0  # retrospective date mentions absorbed, not split

    def flush_dated():
        if cur and cur_lines:
            text = "\n".join(cur_lines).strip()
            if len(text.split()) >= 5:
                title = None
                first = cur_lines[0].strip() if cur_lines else ""
                if first and len(first) < 80 and sum(c.isupper() for c in first) / max(len(first), 1) > 0.6:
                    title = first
                cur["title"] = title
                cur["content"] = text
                cur["words"] = len(text.split())
                entries.append(cur)

    def flush_undated(pdf_label):
        text = "\n".join(pre_lines).strip()
        if len(text.split()) >= 50:
            entries.append({"year": None, "month": None, "day": None,
                            "title": None, "content": text,
                            "words": len(text.split()), "dated": 0,
                            "page": pre_page, "pdf": pdf_label})

    def set_year(y):
        nonlocal year, prev_month, clamped
        if y < year or y > end_year:
            clamped += 1
            return
        year = y
        prev_month = None

    def set_year_abs(y):
        """Trusted year (chapter title / inline date year): clamp to volume."""
        nonlocal year, prev_month, clamped
        if not (start_year <= y <= end_year):
            clamped += 1
            return
        if y != year:
            year = y
            prev_month = None

    def new_entry(mon, day, pno, pdf_label):
        nonlocal year, prev_month
        if prev_month is not None and mon < prev_month:
            set_year(year + 1)  # Dec -> Jan rollover
        prev_month = mon
        return {"year": year, "month": mon, "day": day,
                "title": None, "content": "", "words": 0,
                "dated": 1, "page": pno, "pdf": pdf_label}

    import pymupdf
    for pdf_path, pdf_label in pdf_paths:
        doc = pymupdf.open(pdf_path)
        # buffer all lines for lookahead
        lines = []
        for pno in range(len(doc)):
            for raw in (doc[pno].get_text() or "").split("\n"):
                s = raw.strip()
                if s:
                    lines.append((s, pno))
        chapter_split = False  # first entry started in this chapter?
        title_month = None     # month from a MONTH, YEAR chapter title
        # Pass 1: smooth running year headers. The year repeats on nearly
        # every page, so a lone differing header (OCR: 1855]->1856]) is
        # noise; a genuine Dec->Jan change persists. Remove blips.
        raw_years = []  # (line idx, year)
        for idx, (line, pno) in enumerate(lines):
            ym = YEAR_ONLY.match(line)
            if ym and not DATE_LINE.match(line):
                raw_years.append((idx, int(ym.group("y"))))
                continue
            yr = YEAR_RANGE.match(line)
            if yr:
                raw_years.append((idx, int(yr.group("y1"))))
        smoothed = {}
        for i, (idx, y) in enumerate(raw_years):
            prev_y = raw_years[i - 1][1] if i > 0 else None
            next_y = raw_years[i + 1][1] if i + 1 < len(raw_years) else None
            if prev_y is not None and y != prev_y and (next_y is None or y != next_y):
                if next_y is None:
                    smoothed[idx] = y  # chapter ends in a new year: keep
                else:
                    continue  # lone blip: drop
            else:
                smoothed[idx] = y
        for idx, (line, pno) in enumerate(lines):
            if idx in smoothed:
                set_year_abs(smoothed[idx])
                continue
            if RUNNING_JUNK.match(line):
                continue
            mt = MONTH_TITLE.match(line)
            if mt and not DATE_LINE.match(line):
                # Chapter/month titles ("JUNE, 1858", "PEIIRUARY,").
                # Guard: ordinary short words ("Spend", "BEHAVIOR") also
                # match the shape, so only trust exact month words or
                # titles carrying a comma/year; fuzzy matches need one.
                name, y = mt.group("name"), mt.group("y")
                clean = re.sub(r"[^A-Z]", "", name.upper())
                exact = clean[:3] in MONTHS or clean in (
                    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY",
                    "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER",
                    "NOVEMBER", "DECEMBER")
                if y:
                    # "JUNE, 1858", "lIAY, 1859": the year makes it a
                    # real title even when the month is OCR-garbled
                    set_year_abs(int(y))
                    title_month = fuzzy_month(name)
                    continue
                if exact:
                    title_month = fuzzy_month(name)
                    continue
                if "," in line:
                    # comma but no year ("PEIIRUARY,"): demand a strong
                    # fuzzy match so words like "partiality," don't pass
                    import difflib
                    best = difflib.get_close_matches(
                        clean, ["JANUARY", "FEBRUARY", "MARCH", "APRIL",
                                "MAY", "JUNE", "JULY", "AUGUST",
                                "SEPTEMBER", "OCTOBER", "NOVEMBER",
                                "DECEMBER"], n=1, cutoff=0.7)
                    if best:
                        title_month = fuzzy_month(name)
                        continue
                # else: ordinary content word — fall through
            mon, day = parse_month_day(line)
            via_lead = False
            if mon is None:
                # month-day header with trailing body ("June 2. 8.30 A.M.
                # - Start ...", "Oct. 7, 1842 . A little girl ...")
                lm = LEAD_DATE.match(line)
                if lm:
                    day_tok = lm.group("day")
                    rest = line[lm.end("day"):]
                    if (re.fullmatch(r"[A-Za-z-]+", day_tok)
                            and day_tok.lower() in NUMBER_WORDS
                            and rest.strip()[:1].isalpha()):
                        # prose starting "May I ...", "May first ..."
                        # — not a header
                        pass
                    else:
                        mon = fuzzy_month(lm.group("mon"))
                        day = parse_month_day(
                            lm.group("mon") + " " + day_tok)[1]
                        via_lead = mon is not None and day is not None
            if mon is None and title_month and not chapter_split:
                # day-only chapter opener ("1 . P.M. ...") after a
                # MONTH, YEAR title (mid-chapter "1 ." lines are lists)
                dm = DAY_ONLY.match(line)
                if dm and 1 <= int(dm.group("d")) <= 31:
                    mon, day = title_month, int(dm.group("d"))
            if mon is not None and day is not None:
                bracketed = line.startswith("[") or line.startswith("(")
                if cur is not None and (mon, day) == (cur["month"], cur["day"]):
                    continue  # running-header repeat of current entry
                if (cur is not None and cur["year"] == year
                        and (mon, day) < (cur["month"], cur["day"])
                        and not (mon == 1 and cur["month"] == 12)):
                    # out-of-order header (e.g. OCR-misread day): the entry
                    # continues; only the Dec->Jan rollover moves forward
                    continue
                if not bracketed and is_list_next(lines, idx):
                    continue  # phenology-table date, not an entry header
                iy = INLINE_YEAR.search(line)
                iy_year = int(iy.group("y")) if iy else None
                if iy_year is not None:
                    if not (start_year <= iy_year <= end_year):
                        # a date quoted inside the text (gravestone
                        # "Nov 1 . 1820", battle "April 19, 1775"), not
                        # an entry header
                        continue
                    # explicit year inside the header ("Oct. 21, 1842 .")
                    # is trusted over rollover context
                    set_year_abs(iy_year)
                if (iy_year is None and cur is not None
                        and cur.get("dated") and cur_lines
                        and pno - cur_pno <= 1
                        and (via_lead or chapter_split)):
                    # Retrospective mention mid-entry ("December 29th
                    # there were eight acres...", "...importance that
                    # they had" + "December 29th .", "December 8th,
                    # O.S., the Pilgrims..."): a real new entry never
                    # jumps months forward without a year rollover.
                    # Bracketed running heads are exempt (structural).
                    # Thresholds: LEAD-form (trailing prose) >60d;
                    # bare headers >150d (sparse early journaling has
                    # genuine 40-120d gaps; bigger genuine gaps always
                    # involve a rollover, appendix, or inline year).
                    if bracketed:
                        pass
                    else:
                        try:
                            import datetime as _dt
                            jump = (_dt.date(year, mon, day) - _dt.date(
                                cur["year"], cur["month"], cur["day"])).days
                        except ValueError:
                            jump = 0
                        limit = 60 if via_lead else 150
                        if jump > limit:
                            retro += 1
                            continue
                flush_dated()
                if pre_lines:
                    flush_undated(pre_pdf)
                    pre_lines = []
                cur = new_entry(mon, day, pno, pdf_label)
                cur_lines = []
                cur_pno = pno
                chapter_split = True
                continue
            # ordinary content (or garbled header acting as noise)
            if cur is None:
                if looks_like_header(line):
                    continue
                if not pre_lines:
                    pre_page = pno
                    pre_pdf = pdf_label
                pre_lines.append(line)
            else:
                if looks_like_header(line) and mon is not None:
                    continue  # garbled repeat of a date header
                cur_lines.append(line)
        # chapter boundary: close any open entry so the next chapter
        # starts fresh (undated chapters must not inherit the last date).
        # Month context carries across chapters for Dec->Jan rollover.
        flush_dated()
        cur = None
        cur_lines = []
        doc.close()
    flush_dated()
    if pre_lines:
        flush_undated(pdf_paths[-1][1] if pdf_paths else "unknown")
    if clamped:
        print(f"  warning: {clamped} out-of-range year headers clamped", flush=True)
    if retro:
        print(f"  note: {retro} retrospective date mentions absorbed", flush=True)
    return entries


def download_volume(vol, files):
    name = "journal-i" if vol == "1" else f"journal-{vol}"
    dest = PDF_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in files:
        # Vol I uses bare ChapterN.pdf; others are prefixed (quirks in map)
        if vol == "1" and f.startswith("Chapter"):
            url = f"{PDF_BASE}/{f}"
        elif vol == "5" and f in ("Chapter-3.pdf", "Chapter-4.pdf"):
            url = f"{PDF_BASE}/{f}"
        elif vol == "2" and f == "Chapter-4-1.pdf":
            url = f"{PDF_BASE}/{f}"
        else:
            url = f"{PDF_BASE}/{f}"
        out = dest / f
        if not out.exists() or out.stat().st_size == 0:
            print(f"  downloading {f} ...", flush=True)
            try:
                urllib.request.urlretrieve(url, out)
            except Exception as e:
                print(f"  FAILED {url}: {e}")
                continue
        paths.append((str(out), f))
    return paths


def apply_corrections(entries):
    """Apply visual-verification overrides from corrections.tsv.

    Keyed on (source pdf filename, page, parsed month/day). Returns count.
    """
    path = BASE / "corrections.tsv"
    if not path.exists():
        return 0
    applied = 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            pdf, page, pm, pd, fm, fd = p[0], int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(p[5])
            for e in entries:
                if (e.get("dated") and e.get("pdf") == pdf and e.get("page") == page
                        and e.get("month") == pm and e.get("day") == pd):
                    e["month"], e["day"] = fm, fd
                    applied += 1
    return applied


def main(only_vol=None):
    vols = []
    with open(VOLUME_MAP) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            vols.append({"vol": parts[0], "slug": parts[1],
                         "year": int(parts[2]), "files": parts[5].split()})
    if only_vol:
        vols = [v for v in vols if v["vol"] == only_vol]
    for i, v in enumerate(vols):
        # end year = next volume's start year (volumes are contiguous),
        # except vol 1 (ends 1846, then a gap) and vol 14 (ends 1861)
        if v["vol"] == "1":
            v["end"] = 1846
        elif i + 1 < len(vols):
            v["end"] = vols[i + 1]["year"]
        else:
            v["end"] = 1861

    all_entries = []
    for v in vols:
        print(f"Volume {v['vol']} ({v['slug']})", flush=True)
        paths = download_volume(v["vol"], v["files"])
        entries = parse_volume(paths, v["year"], v["end"])
        n_fix = apply_corrections(entries)
        if n_fix:
            print(f"  applied {n_fix} visual-verification correction(s)", flush=True)
        for e in entries:
            e["volume"] = int(v["vol"])
            e["source"] = f"walden:Journal-{v['vol']}/{e.pop('pdf')}"
        all_entries.extend(entries)
        yrs = sorted({e["year"] for e in entries if e["year"]})
        print(f"  -> {len(entries)} entries, years {yrs[:3]}..{yrs[-3:] if len(yrs) > 3 else yrs}", flush=True)

    # write DB
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author TEXT NOT NULL DEFAULT 'Henry David Thoreau',
        title TEXT, content TEXT NOT NULL, words INTEGER NOT NULL,
        time_to_read INTEGER NOT NULL,
        year INTEGER, month INTEGER, day INTEGER,
        source TEXT NOT NULL, source_item TEXT, page_number INTEGER,
        page_image TEXT, dated INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, page_number INTEGER,
        pdf_file TEXT, extracted_text TEXT, confidence_score REAL,
        created_at TEXT NOT NULL)""")
    now = datetime.now().isoformat()
    for e in all_entries:
        cur.execute(
            """INSERT INTO journal_entries (author, title, content, words,
               time_to_read, year, month, day, source, source_item,
               page_number, page_image, dated, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("Henry David Thoreau", e.get("title"), e["content"], e["words"],
             max(1, e["words"] // 200), e.get("year"), e.get("month"),
             e.get("day"), e["source"], e["source"],
             e.get("page"), None, e.get("dated", 1), now))
    conn.commit()
    conn.close()
    with open(JSON_PATH, "w") as fh:
        json.dump(all_entries, fh, indent=1, default=str)
    print(f"\nTOTAL {len(all_entries)} entries -> {DB_PATH}, {JSON_PATH}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
