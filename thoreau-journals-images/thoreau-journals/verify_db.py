"""Verify DB entries against PDF text with OCR tolerance."""
import sqlite3, pymupdf, re, glob, os, sys
from collections import defaultdict

MONTH_MAP = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,
             'august':8,'september':9,'october':10,'november':11,'december':12,
             'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,
             'sep':9,'sept':9,'oct':10,'nov':11,'dec':12}
OCR_DIGITS = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1",
    "Z": "2", "z": "2", "A": "4", "S": "5", "s": "5", "B": "8", "b": "6", "Q": "2", "g": "9"})
DATE_HEADER = re.compile(
    r'(?:\[?\s*)?\b(January|February|March|April|May|June|July|August|'
    r'September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)'
    r'\s*\.?[ \t]*(?:\n[ \t]*)?[\'\"]?[ \t]*(\d{1,2})', re.IGNORECASE)
OCR_DAY = re.compile(
    r'(?:\[?\s*)?\b(January|February|March|April|May|June|July|August|'
    r'September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)'
    r'\s*\.?[ \t]*(?:\n[ \t]*)?[\'\"]?[ \t]*([A-Za-z])[a-z]?(?:st|nd|rd|th)?', re.IGNORECASE)

def normalize_day(s):
    s = s.strip()
    cleaned = s.translate(OCR_DIGITS)
    try:
        d = int(cleaned)
        if 1 <= d <= 31: return d
    except: pass
    try:
        d = int(s)
        if 1 <= d <= 31: return d
    except: pass
    return None

def src_to_path(src):
    parts = src.split('/')
    vol_name = parts[0].split(':')[1]
    filename = parts[1]
    vol_dir = 'journal-i' if vol_name == 'Journal-1' else vol_name.lower()
    return f'pdfs/{vol_dir}/{filename}'

def main():
    c = sqlite3.connect('thoreau.db')
    rows = c.execute('SELECT id, year, month, day, content, source, page_number FROM journal_entries WHERE dated=1').fetchall()
    by_src = defaultdict(list)
    for r in rows:
        by_src[r[5]].append(r)

    issues = []
    checked = 0
    missing_date = 0
    missing_content = 0
    date_on_diff = 0

    for src in sorted(by_src.keys()):
        pdf_path = src_to_path(src)
        if not os.path.exists(pdf_path):
            issues.append(f"NOPDF {src}")
            continue
        doc = pymupdf.open(pdf_path)
        all_pages = [doc[p].get_text() for p in range(len(doc))]

        for eid, yr, mo, dy, content, source, pno in by_src[src]:
            checked += 1
            if pno >= len(all_pages):
                issues.append(f"PAGENO_OOB {src} id={eid}")
                continue

            page_text = all_pages[pno]
            found_date = False
            # First try numeric day match
            for m in DATE_HEADER.finditer(page_text):
                mon_str = m.group(1).lower()
                day_val = int(m.group(2))
                if MONTH_MAP.get(mon_str) == mo and day_val == dy:
                    found_date = True
                    break
            # Then try OCR-garbled day match
            if not found_date:
                for m in OCR_DAY.finditer(page_text):
                    mon_str = m.group(1).lower()
                    day_str = m.group(2)
                    day_val = normalize_day(day_str)
                    if day_val and MONTH_MAP.get(mon_str) == mo and day_val == dy:
                        found_date = True
                        break

            if not found_date:
                # Search all pages
                for p in range(len(all_pages)):
                    if p == pno: continue
                    for m in DATE_HEADER.finditer(all_pages[p]):
                        mon_str = m.group(1).lower()
                        day_val = int(m.group(2))
                        if MONTH_MAP.get(mon_str) == mo and day_val == dy:
                            date_on_diff += 1
                            issues.append(f"DATE_ON_DIFF_PAGE {src} id={eid}: {yr}-{mo:02d}-{dy:02d} p{p}")
                            found_date = True
                            break
                    if found_date: break
                    # Also check OCR on other pages
                    for m in OCR_DAY.finditer(all_pages[p]):
                        mon_str = m.group(1).lower()
                        day_val = normalize_day(m.group(2))
                        if day_val and MONTH_MAP.get(mon_str) == mo and day_val == dy:
                            date_on_diff += 1
                            issues.append(f"DATE_ON_DIFF_PAGE {src} id={eid}: {yr}-{mo:02d}-{dy:02d} p{p}")
                            found_date = True
                            break
                    if found_date: break
                if not found_date:
                    missing_date += 1
                    issues.append(f"DATE_NOT_FOUND {src} id={eid}: {yr}-{mo:02d}-{dy:02d}")

            content_start = content[:40].replace('\n', ' ').strip()[:20]
            if len(content_start) >= 12:
                found_content = False
                for p in range(max(0, pno-1), min(len(all_pages), pno+2)):
                    if content_start in all_pages[p].replace('\n', ' '):
                        found_content = True
                        break
                if not found_content:
                    missing_content += 1
                    issues.append(f"CONTENT_NOT_FOUND {src} id={eid}: '{content_start}'")

        doc.close()

    print(f"Checked {checked} entries")
    print(f"Issues: {len(issues)}")
    print(f"  DATE_NOT_FOUND: {missing_date}")
    print(f"  DATE_ON_DIFF_PAGE: {date_on_diff}")
    print(f"  CONTENT_NOT_FOUND: {missing_content}")
    print()
    for issue in issues:
        print(f"  {issue}")

if __name__ == '__main__':
    main()
