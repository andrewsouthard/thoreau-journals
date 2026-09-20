# Thoreau Journal — Authoritative Image-Derived Database

> Self-contained implementation plan. A coding agent can execute this top-to-bottom.

**Goal:** Build an authoritative, *date-accurate* database of Henry David Thoreau's
journal entries (1837–1861) keyed by **the date printed on each entry's source page**.

**Preferred source: The Walden Woods Project PDFs** (`walden.org`) — the complete 14-volume
journal, one PDF per year/chapter, each with a **clean, extractable text layer and date
headers** (`[JAN. 3`, `[MARCH 12`) already present in the text. This sidesteps the messy
plain-text editions (Gutenberg / Archive `_djvu.txt`) that the existing
[`andrewsouthard/thoreau-journals`](../../) scrape was built from.

**Fallback source: Internet Archive page scans** (`_jp2.zip`) + local OCR/vision, only if
higher-fidelity transcription of the *page images* is ever needed (e.g. to re-genuinely
transcribe handwriting). The Walden text is the day-to-day default.

**Why not the plain-text editions?** They organize content by *subject title* (SOLITUDE,
SPRING, THE FOG…) with dates scattered inline (`_Oct 22._`), so no parser can reliably attach
one date to one entry. The Walden PDFs carry the date header on the entry itself
(`[OCT. 24`, `Oct. 25.`), so they are the cleanest public-domain date-keyed source.

---

## 1. Why the existing text sources fail (recap)

- **Gutenberg Journal 01 (1837–1846):** year headers + all-caps subject titles + **278 inline
  date markers** mixed with **153 undated prose blocks**. No one-date-per-entry structure.
- **Archive `_djvu.txt`:** OCR-garbled (`Otympia`, `Pyrat`, `Istumra`) and indexed by subject,
  not date.
- **Existing DB (`thoreau_journals.db`):** 448 rows, but only 1837–1846 (1837×55, 1838×83,
  1839×66, 1840×75, 1841×120, 1842×37, 1845×10, 1846×2). Missing 1843–44 and **all of
  1847–1861**. 283 of 448 rows have null titles. Partial scrape.

> The Walden PDFs are the same Bradford Torrey edition as Gutenberg, but re-typeset with a
> **cleaner page layout** — date headers are present and extractable, unlike the raw prose dump.

---

## 2. Sources — Walden Woods Project PDFs (primary)

The Walden Woods Project hosts the complete journal at
`https://www.walden.org/collection/journals/`. Each of the 14 volumes is a page
(`/work/journal-N-<years>/`) containing **one PDF per year/chapter** under
`https://www.walden.org/wp-content/uploads/2016/02/ChapterN.pdf`.

| Volume (Walden) | Years | Chapter(s) |
|---|---|---|
| Journal I  (1837–1846) | 1837–1846 | Chapter1–9 (+IntroductoryMaterials.pdf) |
| Journal II (1850–Sep 1851) | 1850–1851 | Chapter… (enumerate from page) |
| … | (extends to) | 1847–1861 complete |
| Journal XIV (Aug 1860–Nov 1861) | 1860–1861 | … |

Full volume→URL map is on the journals index page (links `/work/journal-ii-1850-september-15-1851/` … `/journal-xiv-august-1-1860-november-3-1861/`).

**Why these are clean (verified):** every page carries an **extractable text layer**
(251/251 pages in Journal I's 9 chapters had text) and date headers appear at line starts
(`[JAN. 3`, `[MARCH 12`, `Oct 25.`). This is the same Torrey edition as Gutenberg but
**re-typeset with date headers preserved**, so a simple line-start parse yields dated
entries — no subject-title guessing needed.

### 2a. Findings from the parse check (Journal I, all 9 chapters)

Quick `pymupdf` audit of `Chapter1-9.pdf` (1837–1846):

| Chapter | PDF pages | with text | distinct date markers | Notes |
|---|---|---|---|---|
| 1 | 13 | 13 | ~14 | 1837, dated entries |
| 2 | 24 | 24 | ~39 | 1838–39 |
| 3 | 20 | 20 | ~19 | 1839–40 |
| 4 | 32 | 32 | ~53 | 1840–41 |
| 5 | 68 | 68 | ~55 | 1841–42, largest |
| 6 | 27 | 27 | ~27 | 1842 |
| 7 | 22 | 22 | ~12 | 1843–44 (sparse) |
| **8** | 19 | 19 | **0** | **The "mutilated journal" (1845–47) — entries are *undated* in the source** |
| **9** | 26 | 26 | ~6 | **Commonplace-book of mostly *undated* transcripts Thoreau drew from for *A Week* / *Walden*** |

**Key finding:** Chapter 7 (1843–44) is genuinely sparse, and chapters 8 & 9 are the
editor's appendices of **undated** material (the mutilated 1845–47 journal and the
commonplace-book). These are *not* parse failures — the source simply has no date for them,
so an authoritative DB must mark them `undated` rather than guess. The **dated** spine
(1837–42) parses cleanly into ~225 date-keyed markers across chapters 1–6.

### 2b. Internet Archive page scans (fallback / higher fidelity)

The complete 20-volume *Writings of Henry D. Thoreau* (Riverside Pocket Edition, 1893).
Volumes **7–20 = the Journal (1837–1861)**. Keep as a fallback only if page-image
transcription is later needed (true manuscript fidelity / spot-verification):

| File | What it is | Use |
|---|---|---|
| `<id>_jp2.zip` | JPEG2000 page scans (e.g. vol 10 ≈ 167 MB) | Image transcription |
| `<id>_orig_jp2.tar` | Full-resolution originals (≈ 485 MB) | Fallback / highest fidelity |
| `<id>_hocr_pageindex.json.gz` | Page → Archive's OCR page index (JSON!) | Page ordering / headings |
| `<id>_page_numbers.json` | Document page-number map (JSON) | Skip flyleaves / plates |
| `<id>_djvu.txt` + `_djvu.xml` | Archive's own OCR text + page coordinates | Cross-check |
| `<id>_hocr.html` | HTML OCR with word coordinates | Word-bounding-box pre-OCR |

**Keys:** `writingsofhenryd0[1–9]thor_3|_2`, `writingsofhenryd10thor_2`,
`writingsofhenryd11thor_1`, `writingshenryda10thorgoog`. Streaming download:
`https://archive.org/download/<id>/<id>_jp2.zip`

#### Gutenberg as a rough-text cross-check

`ebooks/57393` (1837–1846) and `ebooks/59031` (1850–Sep 1851) are the same text in a
messier layout; use them only to **diff content** on those years, not as the source of
truth.

---

## 3. Pipeline — download → parse → date-attach → DB

```
                          ┌────────────────────────────────────────────────────┐
 Walden volume page ────► │ collect ChapterN.pdf (one per year; 14 volumes)    │
                          │ + IntroductoryMaterials.pdf where present            │
                          └───────────┬────────────────────────────────────────┘
                                      ▼
                          ┌────────────────────────────────────────────────────┐
                          │ TEXT-EXTRACTION (fast, no OCR needed)               │
                          │  - pymupdf get_text() per page                      │
                          │  - every page carries a text layer (verified:       │
                          │    251/251 in Journal I)                            │
                          └───────────┬────────────────────────────────────────┘
                                      ▼
                          ┌────────────────────────────────────────────────────┐
                          │ DATE-HEADER DETECTION (regex on line starts)        │
                          │  patterns: [JAN. 3 | [MARCH 12 | Oct 25. |          │
                          │            \nJAN. 3  | 1845-47 | [1837-47           │
                          │  a new date line starts a new entry                 │
                          │  undated blocks (ch.8 mutilated jrnal, ch.9         │
                          │  commonplace-book) tagged 'undated'                 │
                          └───────────┬────────────────────────────────────────┘
                                      ▼
                          ┌────────────────────────────────────────────────────┐
                          │ SPLIT → entries: content until next date (or        │
                          │ chapter end); merge multi-page same-date runs       │
                          └───────────┬────────────────────────────────────────┘
                                      ▼
                          ┌────────────────────────────────────────────────────┐
                          │ CLEAN & VERIFY (optional, hardware-dependent)       │
                          │  - low-confidence / OCR-garbled lines → local OCR   │
                          │    (tesseract) on the page IMAGE if needed          │
                          │  - or a local VLM (see §4) as a spot verifier       │
                          └───────────┬────────────────────────────────────────┘
                                      ▼
                          ┌────────────────────────────────────────────────────┐
                          │ ASSEMBLY → journal_entries                          │
                          │  year from volume/chapter + month/day from date-line│
                          │  store source ref: walden ChapterN.pdf + page #     │
                          │  (archive item + jp2 page # kept for back-ref)      │
                          └────────────────────────────────────────────────────┘
                                      ▼
                        SQLite (thoreau.db) + JSON export (mirrors
                        existing thoreau_journals schema)
```

### Output schema (forward-compatible with existing DB)

`journal_entries` (SQLite table), extending the current shape:

```sql
CREATE TABLE journal_entries (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  author         TEXT NOT NULL DEFAULT 'Henry David Thoreau',
  title          TEXT,               -- first-line heading if any (may be NULL)
  content        TEXT NOT NULL,      -- full transcription
  words          INTEGER NOT NULL,
  time_to_read   INTEGER NOT NULL,
  year           INTEGER, month INTEGER, day INTEGER,  -- from date-line; NULL if undated
  source         TEXT NOT NULL,      -- 'walden:ChapterN' | 'ia:<item>_jp2' | 'manual'
  source_item    TEXT,               -- walden chapter / archive item
  page_number    INTEGER,            -- PDF page (or image page) number
  page_image     TEXT,               -- source PDF URL / archive image path
  dated          INTEGER NOT NULL DEFAULT 1,  -- 0 for genuinely undated entries
  created_at     TEXT NOT NULL
);
```

Plus a `pages` table for auditing raw page transcription / errors, and a JSON export
`thoreau.json` mirroring the same objects.

---

## 4. OCR / local vision — now just a *verify* tool, not the core

Because the Walden PDFs ship with an extractable text layer, **no OCR is needed for the main
pipeline**. OCR / a local VLM are only used to *verify or repair* the few low-quality lines:

**Hardware caveat (must be decided before start):** the current Hermes host is a
**Raspberry Pi (aarch64, no NVIDIA GPU, 8-ish GB RAM)**. Running a vision LLM over the whole
corpus locally on a Pi is **impractically slow**. So:

1. **Main path (cheap, on the Pi):** `pymupdf` text extraction + line-start regex parsing —
   no OCR at all. Fast, deterministic.
2. **Verify/repair (tesseract on the Pi, zero new hardware):** for pages whose extracted text
   looks garbled, run `tesseract`/`ocrmypdf` on the rendered page image and diff. Handles the
   printed 1893 type well; only manuscript-scrawl-heavy pages struggle.
3. **Optional VLM spot-check (on a GPU/Apple-Silicon box):** run **Ollama / llama.cpp —
   `moondream`, `llava`, `qwen2.5-vl`, `llama3.2-vision`** over a sub-sample of low-confidence
   pages. Endpoint: OpenAI-compatible (`http://localhost:11434/v1`). Reuse the Hermes
   `apple-silicon-local-llm` setup if a capable box exists; otherwise skip.

> The earlier Archive-`_jp2.zip`-as-core / full-corpus-VLM idea is **superseded**: the Walden
> text layer removes the need to OCR ~95% of pages. Keep Archive images only if true
> manuscript-fidelity transcription of a specific page is later wanted.

---

## 5. Implementation steps (an agent executes these)

### Step 0 — Repo + venv
- Output folder `thoreau-journals/` in this collab repo (plan lives at
  `thoreau-journals-images/PLAN.md`).
- `python3 -m venv .venv && . .venv/bin/activate`
- `pip install pymupdf requests`
- `sudo apt install tesseract-ocr ocrmypdf` (only if/when verify/repair is needed)

### Step 1 — Inventory Walden sources (authoritative map)
- Fetch `https://www.walden.org/collection/journals/` (full text, not JS).
- Extract the 14 `/work/journal-*-<years>/` links → build `volume_map.tsv`
  (volume → years → chapter links).
- Save each volume's HTML to discover its `ChapterN.pdf` + `IntroductoryMaterials.pdf` URLs.

### Step 2 — Download & extract (pilot: Journal I, 1837–1846)
- Download `Chapter1-9.pdf` + `IntroductoryMaterials.pdf` for Journal I (~20 MB total).
- `pymupdf` → per-page text. Journal I: 251/251 pages carry text (verified).

### Step 3 — Date-header detection
- Regex on line starts: `^[\[\(]?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{1,2}(?:st|nd|rd|th)?\.?[\)\]]?`
  plus year-only or year-range headers (`1845-47`, `[1837-47`).
- A new date header starts a new entry. Blocks with no date header (ch.8 mutilated journal,
  ch.9 commonplace-book) → `dated=0`, `year/month/day` NULL.
- Emit `pages_with_dates.tsv` → correct the volume→year map.

### Step 4 — Extract entries
- Walk chapter pages in order; split content at each date header; merge same-date runs that
  span pages. Body = text until the next date header (or chapter end).
- Normalize date abbreviations (`JAN.` → January, `MARCH I` → March 1) via a small lookup.

### Step 5 — Verify & repair (hardware-dependent)
- Flag pages whose extracted text has low word-rate / long-garbled runs.
- For those: render page to image (pymupdf) → `tesseract` → diff, keep the better; or route
  to a local VLM on a capable box if available.

### Step 6 — Assemble & load
- Insert into SQLite `journal_entries`; write `thoreau.json` (mirrors existing schema + new
  `source`/`dated` fields).

### Step 7 — Validation & extend
- Count checks: rows per year should be dense across 1837–1861; spot-check dates against
  Gutenberg text on 1837–46 (loose reference only).
- Sample audit: hand-read 5 random PDF pages; confirm extraction matches.
- Optional: regenerate `andrewsouthard/thoreau-journals` DB from this authoritative dataset,
  or insert authoritative rows for years the old scrape missed (1843–44, 1847–1861).

---

## 6. Scope & cost estimate (volume approximation)

- **Volumes:** 14 journal volumes (Walden), ~9 chapter PDFs for Journal I (1837–46) alone;
  full set spans 1837–1861.
- **Downloads:** small — each `ChapterN.pdf` is 1–6 MB (Journal I summed ~23 MB). Total across
  all volumes is a few hundred MB. (Archive `_jp2.zip` totals 3–6 GB, only if needed.)
- **Parse time (Pi):** `pymupdf` extraction + regex is seconds per volume; the whole set
  parses in well under an hour. No OCR in the main path.
- **OCR/verify (only for low-quality pages):** ~2–5 s/page with tesseract; optional VLM
  spot-check on a capable local box if available.

---

## 8. Execution status (2026-09-11) — COMPLETE

Implemented in `thoreau-journals/`: `build_db.py` (universal parser),
`volume_map.tsv` (14-volume chapter inventory), `corrections.tsv` (1
visual-verified override), `pdfs/journal-N/` (131 PDFs,
~332 MB), `thoreau.db` + `thoreau.json` (**2714 entries: 2692 dated,
22 undated**).

Per-year dated counts: 1837×30, 1838×49, 1839×41, 1840×57, 1841×100,
1842×31, 1845×8, 1846×2, 1850×29, 1851×181, 1852×253, 1853×217, 1854×243,
1855×218, 1856×207, 1857×249, 1858×264, 1859×227, 1860×245, 1861×30.
Gaps (1843–44, 1846–49) are source-real: the edition has no dated entries
there (ch.8 mutilated journal + ch.9 commonplace-book are undated appendices).

Parser rules (all in `build_db.py`): bracketed running heads split only on
date change; year context from running `[YEAR` heads with blip-smoothing
(single OCR-garbled `1856]`-for-`1855]` dropped); Dec→Jan rollover carried
across chapter boundaries; phenology-table dates rejected via 3-line
lookahead; out-of-order headers treated as continuations; inline years
(`Oct. 21, 1842 .`) and `MONTH, YEAR` chapter titles (fuzzy, OCR-tolerant)
trusted; day-only openers (`1 . P.M.`) only at chapter starts.

Known faithful-to-source quirks (not parse errors): 18 seam-overlap duplicate
dates (same calendar day printed in two chapters/volumes, different texts);
17 backward steps, all verified against the page text (e.g. `Jun . 7 .`
entries describing frozen rivers — Torrey/Thoreau misprints, kept per the
date-on-the-page principle); Ch.8/9 vol 1 + vol-2 front matter kept as
`dated=0`. Genuinely dated fragments inside appendices kept with inline
years (e.g. Ch.9 `Sept. 29, 1842`). Supersedes `process_journal_enhanced.py`
(Journal-I pilot, hardcoded year 1837 — do not use).

### Audit (2026-09-11, independent re-check vs the PDFs)

- **Coverage:** DB words ÷ raw PDF words = 95.9–97.4% per volume (remainder
  is running heads / page numbers / dropped header noise).
- **Anchors:** first entry Oct 22 1837 ("So I make my first entry") and last
  entry Nov 3 1861 both verified verbatim; all 14 volume seams match their
  stated ranges to the day (except vol 9 ends Aug 6 vs title "Aug 7", and
  vol 13 opens with a Nov 30 bridge entry shared with vol 12).
- **Random sample:** 12/12 entries verified — date header and content start
  both present on the recorded PDF page (including tricky cases: `Jan. 4.`
  inline header, `July 14 .` mid-page, `[AuG . 31` OCR case, `Oct . i .`
  roman numeral).
- **Bugs found & fixed:** (1) `Sept` headers never matched (alternation had
  only `Sep`) — 199 September entries had been lost; (2) gravestone
  inscription `Nov 1 . 1820` created a false Nov-1850 mega-entry swallowing
  June–Oct 1850 — inline years outside the volume range now veto the split;
  (3) lone OCR-garbled year running-heads (`1856]`-for-`1855]`) — removed by
  blip-smoothing; (4) mid-chapter `1 .` list items split via stale month
  titles — day-only headers now chapter-openers only; (5) `MONTH_TITLE`
  ate ordinary short words (`Spend`, `BEHAVIOR`, `boat,`) — now requires an
  exact month word, a year, or a strong (0.7) fuzzy match with comma;
  footnote fragments (`9.98.]`) no longer match `DAY_ONLY` (period must not
  be followed by a digit); (6) `Feb . 29.` 1855 corrected to Feb 22 from
  the page image, via new `corrections.tsv` visual-override mechanism.
- **Remaining, all source-faithful:** 15 seam-overlap duplicate dates;
  backward steps only from print misprints / appendix arrangement; both
  remaining `Feb 29` rows (1840, 1852) visually confirmed as printed
  leap-day entries.
- **Final totals:** 2611 entries (2581 dated, 30 undated), 0 nulls, 0 word-count mismatches, 0 invalid dates, JSON↔DB identical. Capture ≈97.8%.
- **Retro-guard system (final):** `via_lead` flag for LEAD_DATE matches; `chapter_split` flag; same-page/adjacent-page (`pno - cur_pno <= 1`) constraint on the jump heuristic. Retrospective date mentions absorbed: 11. All five originally-flagged cases (Dec 29 vol 8/13, Dec 8 O.S. vol 2, Nov 12 1845, Jun 28 1856) correctly handled — Dec 29 and Dec 8 absorbed as prose, Nov 12 and Jun 28 retained as genuine entries.
- **Bugs fixed in this pass:** (1) `LEAD_DATE` over-matching ordinary prose like `deci.sa...` and `Junes Thornton` — tightened to require OCR-style month tokens only, `fuzzy_month` cutoff raised to 0.85 with length≥4 guard; (2) `DAY_ONLY` leading-dot false match on wrapped fragments; (3) G1 guard was firing across chapter boundaries on stale `cur` — added `cur_pno` tracking and `pno - cur_pno <= 1` constraint; (4) `fuzzy_month` Hamming-1 collisions (NOT→NOV, CAN→JAN, OUT→OCT, DAY→MAY, MORNING→MAR) — restricted to OCR-suspicious tokens (brackets/dots) or full names (len≥4).
- **Remaining, all source-faithful:** 18 seam-overlap duplicate dates; 7 backward steps (all verified print misprints / appendix arrangement); 30 undated entries (front matter, appendices, phenology tables).
### Final verification pass (2026-09-18)

- **Tool:** `verify_db.py` — automated page-by-page regex check of all 2581 dated entries against PDF text, with OCR digit tolerance.
- **Result:** 35 discrepancies (1.4%), down from 40 after regex fix (`\b` word boundaries + numeric-only day capture + separate `OCR_DAY` for single-letter artifacts).
- **All 35 remaining issues are source-faithful:** multi-day continuation entries (Category A), OCR misread days resolved by running-header context (Category B), commonplace-book pages (Category C), cross-page date mismatches (Category D), content spanning pages (Category E).
- **`CHECK.md`** — full verification log with per-issue categorization.


## 7. Open decisions (flag before execution)

1. **Volume set.** All 14 journal volumes (complete 1837–1861) vs. only the missing years
   (1843–44, 1847–1861) to complement the existing 1837–46 scrape.
2. **Scope of "authoritative"** — replace the existing DB entirely, or produce a parallel
   authoritative DB and keep the curated 448-row one for the RSS feed.
3. **Handling of genuinely undated material** (ch.8 mutilated journal 1845–47, ch.9
   commonplace-book): mark `dated=0` and attach to the nearest year-range header, or exclude
   from the dated index and keep in a separate appendix. Recommend keeping with `dated=0`.
4. **Verify tooling.** Pi-only tesseract verify (default) vs. also routing low-confidence
   pages to a local VLM on a GPU/Apple-Silicon box. Needs a target box + Ollama/llama.cpp if
   the latter.
5. **Provenance/licensing.** All 1893-edition scans are public-domain (Walden & archive.org
   "opensource" items) — no copyright concern; keep `source_item`/`page_image` for provenance.