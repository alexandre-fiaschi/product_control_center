# Claude-based Release Notes Extraction

**Date:** 2026-04-11
**Status:** Validated by hand in claude.ai chat against `8.0.18.1 - Release Notes.pdf`. Implementation pending.

## Why this exists

Unit 4 (Block B prototype) tried two heuristic PDF extractors — `opendataloader-pdf` in `fast` mode (Java, font-size based) and `hybrid` mode (IBM Docling, ML layout). Both produced output below acceptable workflow quality despite ~900 lines of filters in `scripts/test_docx_conversion.py`. The fundamental problem: PDFs have no semantic structure, so every extractor reverse-engineers it from font sizes / bounding boxes / ML guesses, and they all get it wrong in different places.

This document captures the alternative approach: **send the PDF directly to Claude, get a structured JSON record back, render the DOCX from the record.** Claude reads the PDF visually and returns clean structure in one shot. No heuristics, no filters.

The structured record also becomes a **persistent source of truth** stored in `state/release_notes_items/<product>.json` (per [PLAN_DOCS_PIPELINE.md](PLAN_DOCS_PIPELINE.md) — see the Unit 4 / Unit 5 sections). DOCX generation reads the record. The frontend can read the record. If Cyberjet ever delivers source `.docx` files we replace the extraction step but keep the same downstream.

## Manual validation in claude.ai

Before building any code, we tested the approach by hand: pasted `8.0.18.1 - Release Notes.pdf` into a claude.ai chat with the prompt below and inspected the output.

**Result: excellent.** Claude correctly identified all 13 items across 3 sections (`New Features`, `Defect fixes`, `Not tested`), split out customer codes (HAL, PLM, ETH, FFT, ICL, JBU, VKG), generated plain-English summaries, anchored every screenshot to its parent item, and emitted zero OCR noise from inside screenshots and zero CAE page chrome. This is what fast and hybrid couldn't do after a day of filter tuning.

## The prompt

Pasted into claude.ai with the PDF attached:

```
You are extracting structured data from a release notes PDF.

Read the attached PDF and output a JSON array. Each element is one AM
item (one feature, fix, or note) in the order it appears in the document.

For every item, output an object with these fields:

- section: the section name from the PDF, copied verbatim ("Release
  Features", "Defect Fixes", "Not Tested", etc.)
- am_card: the AM number, e.g. "AM3394"
- customers: list of customer codes associated with the item, e.g.
  ["FFT"], ["SWR", "PLM"], ["HAL"]. Empty list if none. An item can
  belong to multiple customers.
- title: the item title with the AM card and customer codes stripped,
  single line, no trailing punctuation
- summary: one short sentence (max ~20 words) in plain English
  describing what this item changes. Paraphrase, don't copy the title.
- body: an array of content blocks in document reading order

Each body block is one of:

- {"type": "paragraph", "text": "..."} — body text, verbatim from the PDF
- {"type": "subheading", "text": "..."} — inline labels like
  "Bug Description" or "After correction"
- {"type": "image", "page": N, "describes": "..."} — a screenshot,
  where N is the page it appears on and describes is a short phrase
  explaining what the screenshot shows in context

Rules:
- Walk the document top to bottom in real reading order
- Skip page headers, footers, page numbers, the Cyberjet logo, and the
  small on-page table of contents on the cover
- Do NOT transcribe text that is INSIDE a screenshot (UI labels, dialog
  buttons, form fields). Screenshots are referenced as image blocks only.
- If you see a screenshot that visually belongs to a specific AM item,
  place its image block inside that item's body
- Never invent AM codes. If an item has no AM code, skip it.

Output ONLY the JSON array, no commentary.
```

## Sample output (excerpt from `8.0.18.1 - Release Notes.pdf`)

Full output is 13 items across 3 sections. First two items shown to illustrate the structure:

```json
[
  {
    "section": "New Features",
    "code": "AM1393",
    "customer": "HAL",
    "title": "Message processor/Admin: Adding characters replacement feature for freetext uplink",
    "summary": "Lets admins define character replacements applied to free-text uplink messages before they are sent.",
    "body": [
      {"type": "subheading", "text": "Remark"},
      {"type": "paragraph", "text": "The following characters cannot be entered from the hexadecimal field because they are not preserved when converting to ASCII text via a text field:"},
      {"type": "paragraph", "text": "00 => NULL"},
      {"type": "paragraph", "text": "0A => LF"},
      {"type": "paragraph", "text": "0D => CR"},
      {"type": "subheading", "text": "Setting"},
      {"type": "paragraph", "text": "Go to \"Global References->Character Replacement\" menu :"},
      {"type": "image", "page": 2, "describes": "Navigating to Global References > Character Replacement in the OpsComm admin menu"},
      {"type": "paragraph", "text": "Select \"Uplink\" tab, click on \"Modify\" then select \"New\" or \"Modify\""},
      {"type": "image", "page": 2, "describes": "Character Replacement screen with the Uplink tab and Modify button highlighted"},
      {"type": "paragraph", "text": "Replacement of ABC with EFGHI :"},
      {"type": "image", "page": 3, "describes": "Dialog configuring a replacement of input ABC with output EFGHI"},
      {"type": "subheading", "text": "Uplink message"},
      {"type": "image", "page": 3, "describes": "New Uplink composition window with a free-text message that contains -ABC-"},
      {"type": "subheading", "text": "Result"},
      {"type": "image", "page": 3, "describes": "Resulting ACARS message where ABC has been replaced by EFGHI before uplink"}
    ]
  },
  {
    "section": "New Features",
    "code": "AM2865",
    "customer": "PLM",
    "title": "JS Comm Admin - Fleet - Add virtual aircraft checkbox filter",
    "summary": "Adds a checkbox in the Fleet screen to include or exclude virtual aircraft from the display.",
    "body": [
      {"type": "subheading", "text": "Active filter"},
      {"type": "image", "page": 4, "describes": "SQL Server query against the FLEET table filtering on VIRTUAL_AC"},
      {"type": "subheading", "text": "Applying filter"},
      {"type": "image", "page": 4, "describes": "Fleet display filters panel with the Include virtual aircraft checkbox ticked"},
      {"type": "subheading", "text": "Deactivate filter"},
      {"type": "image", "page": 5, "describes": "SQL Server query on FLEET with the virtual aircraft filter removed"},
      {"type": "subheading", "text": "Result :"},
      {"type": "image", "page": 5, "describes": "Fleet screen after unchecking Include virtual aircraft, showing only real aircraft"}
    ]
  }
]
```

### What worked

- **Sections named verbatim** ("New Features", "Defect fixes", "Not tested") — no normalization needed
- **AM codes correctly split** from customer codes (HAL, PLM, ETH, FFT, ICL, JBU, VKG)
- **Empty customer string** for items without one (e.g. AM2988, AM2839, the three "Not tested" items)
- **Image-to-item anchoring is correct**: the Character Replacement screenshots stay with AM1393, the diversion screenshots stay with AM2839, etc. — no leakage between items
- **Subheadings** ("Remark", "Setting", "Result", "Bug Description", "After correction") emitted as the right type, not as headings
- **Page numbers** on images for our extraction lookup
- **Empty body** for "Not tested" placeholder items (AM2970) — exactly how the example output DOCX handles them
- **Zero OCR garbage** from inside screenshots — Claude understands a screenshot is a screenshot, not text to transcribe
- **Zero CAE page chrome** ("Jetsched Communications Release Note", "AIR TRANSPORT INFORMATION SYSTEMS", "SAS CYBERJET …", "Page X sur N") — Claude knows it's page header/footer
- **Plain-English summaries** that paraphrase rather than copy the title

### Things to verify in implementation

- **Page numbering convention** — Claude uses PDF page numbers (the cover is page 1). When we extract images via pdfplumber for the pre-extraction step, we need to use the same convention so `{"image_id": "p2_img1"}` references an image we extracted from page 2.

### Spot-checks against the source PDF (manual verification)

- **AM2904 customer = "ETH"** — confirmed: the PDF body literally reads `(AM2904) ETH - MIAM - Configurable response code F or E`. Not an inference.

## Image handling — pre-extract and tag, never reference by page alone

The current sample output references images as `{"type": "image", "page": N, "describes": "..."}`. That works for short PDFs with one image per page but breaks down on real release notes — the V8.0.18.1 sample has multiple screenshots per page in many places, and "page N" alone is ambiguous.

The fix: **extract all images from the PDF up front, give each a stable ID, store them on disk, and pass Claude a manifest of IDs.** Claude then references images by ID, not by page.

### Why we want this regardless of ambiguity

1. **Self-contained record.** Once extracted, the record + the image folder is everything you need to render the DOCX. Re-rendering after a template change doesn't re-parse the PDF.
2. **Frontend can show images.** The same `<image_id>.png` files served from the backend power the eventual review UI without any extra extraction step.
3. **Deterministic IDs.** Image IDs survive re-extraction. If we re-run Claude on the same PDF (e.g. extractor version bump), the IDs don't change, so any human edits to the record that reference image IDs stay valid.
4. **Caption / alt-text storage.** Each image carries its Claude-generated `describes` caption alongside the bytes. The frontend can show captions; screen readers can use them; we can search the caption text later if we want.
5. **Cyberjet handoff stays clean.** When CJ delivers source `.docx` files, we extract images from the docx the same way (with `python-docx`), use the same ID convention (`p1_img1` is meaningless for a docx, we'd use `img1`, `img2`, …), and the downstream rendering stays unchanged.

### Image storage layout

Per release note, images live next to the PDF in the patches folder:

```
patches/
└── ACARS_V8_1/
    └── 8.1.12.0/
        └── release_notes/
            ├── 8.1.12.0 - Release Notes.pdf       ← source from Zendesk
            └── images/                              ← NEW
                ├── manifest.json                   ← {id, page, bbox, sha, describes}
                ├── p1_img1.png                     ← Cyberjet logo (probably filtered later)
                ├── p2_img1.png                     ← Swagger popup
                ├── p2_img2.png                     ← EOBT screenshot
                ├── p3_img1.png
                ├── p3_img2.png
                └── p4_img1.png
```

Mirrors how the binaries pipeline already stores patch files next to each version. No new top-level directory needed.

The `manifest.json` schema:

```json
{
  "extracted_at": "2026-04-11T...",
  "extractor": "pdfplumber",
  "extractor_version": 1,
  "images": [
    {
      "id": "p2_img1",
      "page": 2,
      "index_on_page": 1,
      "bbox": [70.5, 412.4, 540.2, 555.8],
      "width_px": 1248,
      "height_px": 372,
      "format": "png",
      "sha256": "8c1f...",
      "describes": null
    }
  ]
}
```

`describes` starts as `null` — Claude fills it in during extraction and we update the manifest after the extraction call returns.

### ID convention

`p{page}_img{index}` where both numbers are 1-indexed:
- `p1_img1` = first image on page 1
- `p2_img2` = second image on page 2
- etc.

Index ordering is **top-to-bottom, then left-to-right** by bbox top-y (matching reading order), so `p2_img1` is always the topmost image on page 2.

### How extraction and the Claude call connect

The flow becomes:

```
┌──────────────────────────────────┐
│ 1. PDF lands on disk             │  (Unit 3: Zendesk fetch)
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 2. Extract images (pypdfium2)    │  Save PNG bytes per image under
│                                  │  release_notes/images/
│                                  │  Compute bbox, dims, sha256, IDs
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 3. Pre-filter chrome images      │  Logo, tiny icons, page bands marked
│                                  │  `chrome: true`, NOT sent to Claude
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 4. Build user message:           │  - PDF as document content block
│                                  │  - Each content image as its own
│                                  │    image content block, in the
│                                  │    same order as the manifest
│                                  │  - Manifest text listing IDs +
│                                  │    page / position / dimensions
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 5. Call Claude with the PDF,     │  Claude sees both the rendered PDF
│    image blocks, tool definition │  AND each image separately. Matches
│                                  │  screenshots to IDs visually.
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 6. Claude calls                  │  Each call references images by ID
│    save_release_note_item        │  {"type":"image","image_id":"p2_img1",...}
│    once per AM item              │
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 7. Collect items, validate,      │  Validate: every image_id exists in
│    persist record                │  the manifest.
└─────────────┬────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│ 8. DOCX render reads record      │  No PDF parsing at render time.
│    + images/ from disk           │  doc.add_picture(images/p2_img1.png)
└──────────────────────────────────┘
```

The user message we build for step 4 looks like:

```
[document block: <PDF bytes>]

[image block: <p2_img1.png bytes>]
[image block: <p2_img2.png bytes>]
[image block: <p3_img1.png bytes>]
[image block: <p4_img1.png bytes>]
[image block: <p4_img2.png bytes>]

[user text]:
Image manifest (use these exact IDs in image blocks). Each image block
above corresponds to one of these IDs, in the same order.

p2_img1 — page 2, upper area, 1248×372 px
p2_img2 — page 2, middle area, 884×440 px
p3_img1 — page 3, upper area, 1820×1320 px
p4_img1 — page 4, upper area, 802×600 px
p4_img2 — page 4, lower area, 1620×1180 px

When you reference an image from the PDF, match it visually against
the image blocks above and use the exact ID. Never invent IDs.
Never reference an image that isn't in this list.
```

Chrome images (logo, tiny icons, page bands) are pre-filtered and never appear in the image blocks or the manifest text. Position strings ("upper area", "lower area") come from the bbox y-coordinates to give Claude a rough spatial hint. No captions, no AI-generated descriptions — just the factual metadata we already computed during extraction.

### Why send images as separate content blocks

Giving Claude each image as its own content block solves the identity problem:
- Claude sees the embedded screenshot inside the PDF AND the isolated image side-by-side
- Visual comparison is trivial for Claude — no guessing, no reading-order inference
- Cost: ~1500 input tokens per image. For a 32-page PDF with 30 content images, ~45k extra tokens, ~$0.15. Negligible.

### Pre-filtering chrome images during extraction

Before Claude even sees the manifest, we filter out images that are obviously page chrome:

- The Cyberjet logo (small image, top-left of every page, appears N times where N = page count)
- Page-band decorations
- Anything with width × height < a small threshold AND positioned in the top-of-page band

These get extracted and saved (so we have a complete record), but they're flagged `chrome: true` in the manifest and **excluded from the manifest text passed to Claude**. Claude only sees real content images.

The existing `is_page_header_logo` heuristic from `scripts/test_docx_conversion.py` (top-of-page position + small bbox) ports directly into the new extractor.

### Updated tool schema for `save_release_note_item`

The body block for images changes from `page` to `image_id`. Body block types in v1:

| Block type | Required fields | Notes |
|---|---|---|
| `paragraph` | `text` | Body text, verbatim |
| `subheading` | `text` | Inline label like "Bug Description", "After correction" |
| `image` | `image_id`, `describes` | `image_id` matches `^p\d+_img\d+$` and must exist in the manifest |
| `list` | `ordered`, `items` | `ordered: bool`, `items: list[str]`. Bulleted or numbered list. |
| `table` | `headers`, `rows` | `headers: list[str]`, `rows: list[list[str]]`. Real data tables. |
| `note` | `text` | "Remark:" / "Note:" callout block |
| `warning` | `text` | "Warning:" / "Caution:" callout block |
| `code` | `text` | Raw machine-formatted text: log lines, SQL queries, ACARS / AFTN messages, flight plan / X19 / FPL payloads, JSON / XML snippets, command output |

Prompt rules we add for the new types:
- **list**: when you see a real bulleted or numbered list, group all items into a single `list` block — never emit each item as a separate paragraph.
- **table**: when you see a real data table with headers and rows, emit it as a single `table` block — never flatten to paragraphs.
- **note** / **warning**: use these for callout-style admonitions like "Remark:", "Note:", "Warning:", "Caution:".
- **code**: use for any raw machine-formatted content (log snippets, SQL, ACARS messages, flight plan payloads, JSON, XML, command output). Verbatim — preserve line breaks and spacing.

Rendering for v1 doesn't matter — we classify everything correctly now and pick the Flightscape style mapping later. Worst case, unsupported types fall back to `Body Text`.

Validation:
- Schema enforces the regex pattern on `image_id`
- Python validates that the ID actually exists in the manifest after the tool call returns
- If Claude references an unknown ID, the validator raises and we retry the call with a feedback message ("image_id 'p9_img3' is not in the manifest, valid IDs are: ...")

### Updated Pydantic model

```python
class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str

class SubheadingBlock(BaseModel):
    type: Literal["subheading"] = "subheading"
    text: str

class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    image_id: str  # e.g. "p2_img1", validated against the manifest
    describes: str

class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[str]

class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    headers: list[str]
    rows: list[list[str]]

class NoteBlock(BaseModel):
    type: Literal["note"] = "note"
    text: str

class WarningBlock(BaseModel):
    type: Literal["warning"] = "warning"
    text: str

class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    text: str

BodyBlock = Annotated[
    ParagraphBlock | SubheadingBlock | ImageBlock | ListBlock | TableBlock | NoteBlock | WarningBlock | CodeBlock,
    Field(discriminator="type"),
]
```

`page` is gone from `ImageBlock`. Page is implied by the ID and stored in the manifest, not in the record. Decoupling means we can move images around (re-extract, renumber) without touching every record.

### Updated render step

`lookup_image(record, image_id)` now resolves to `<source_pdf_dir>/images/<image_id>.png` directly. No pdfplumber call at render time. Faster, simpler, and the render works even if pdfplumber isn't installed.

```python
def lookup_image(record: ReleaseNoteRecord, image_id: str) -> Path | None:
    images_dir = Path(record.source_pdf_path).parent / "images"
    img_path = images_dir / f"{image_id}.png"
    return img_path if img_path.exists() else None
```

### New file: `backend/app/integrations/pdf/image_extractor.py`

A small module that:

- Opens a PDF with pdfplumber
- Walks every page, extracts every embedded image as PNG bytes
- Computes bboxes, dimensions, sha256 hashes
- Sorts images per page by reading order (top-to-bottom)
- Assigns IDs (`p{page}_img{index}`)
- Flags chrome images (logo, small top-band)
- Writes PNGs to `<pdf_dir>/images/`
- Writes `manifest.json` next to them
- Returns the manifest object so the extractor can pass it to Claude

This gets called once per release note, right after Zendesk fetch and right before the Claude extraction. It's idempotent: if the manifest already exists and the source PDF hash matches the manifest's recorded hash, we skip re-extraction.

### What this changes in the implementation plan

Adding to the **Files to create** list in Unit 4.5:

- `backend/app/integrations/pdf/__init__.py`
- `backend/app/integrations/pdf/image_extractor.py` — pdfplumber-based extractor described above
- (the patches/.../release_notes/images/ directory is created on demand, not committed)

Adding to **Files to modify**:

- `backend/app/state/release_notes_models.py` — `ImageBlock` carries `image_id` instead of `page`. Add `ImageManifest` and `ManifestImage` models for the manifest.json file.
- `scripts/test_docx_conversion.py` — `--mode claude` now does: image extraction → manifest → Claude call → record → render. Render step uses `lookup_image` from disk, not pdfplumber.

### State model integration (no changes needed)

The new fields on `ReleaseNotesState` (`record_extracted_at`, `record_extractor_version`) cover this. The manifest is a sibling artifact next to the PDF; its existence is implied by the record being present.

If we ever want to track manifest staleness independently, we add `images_extracted_at` later. Don't bother for v1.

## Implementation plan

This becomes a new unit. Calling it **Unit 4.5** because it sits between the prototype gate (Unit 4) and production integration (Unit 5).

### Unit 4.5 — Claude extractor + record store

**Goal:** replace the heuristic extraction in `scripts/test_docx_conversion.py` with a Claude API call that produces a structured release-note record. Store the record in a per-product index file. The DOCX renderer becomes a thin walker over the record.

**Files to create:**

- `backend/app/integrations/claude/__init__.py`
- `backend/app/integrations/claude/client.py` — Anthropic SDK wrapper, handles auth, retries, timeouts
- `backend/app/integrations/claude/extractor.py` — `extract_release_note(pdf_path) → ReleaseNoteRecord` using tool-use with the schemas defined in this doc
- `backend/app/state/release_notes_models.py` — Pydantic models for the record schema (`ReleaseNoteRecord`, `ReleaseNoteSection`, `ReleaseNoteItem`, `ParagraphBlock`, `SubheadingBlock`, `ImageBlock`, `ReleaseNotesIndex`)
- `backend/app/state/release_notes_store.py` — `load_release_notes(product_id)`, `save_release_notes(...)`, `get_record(...)`, `upsert_record(...)`. Mirrors `state/manager.py`. Uses the same atomic-write pattern.
- `state/release_notes_items/` directory — gitignored except for a placeholder
- `docs_example/conversion_prototype/.cache/claude/` — cached Claude outputs per PDF (one JSON per release note, keyed by source PDF hash)

**Files to modify:**

- `scripts/test_docx_conversion.py` — add `--mode claude`. The Claude branch:
  1. Computes `sha256(pdf_bytes)`
  2. Checks `.cache/claude/<hash>.json` — if present and `--no-cache` not set, reuse
  3. Otherwise calls `extractor.extract_release_note(pdf_path)` → record
  4. Caches the record
  5. Walks the record into the Flightscape template using a *new* simple emitter (~150 lines, replaces the ~600 lines of fast/hybrid filters)
  6. For images: extracts them on-the-fly from the source PDF via pdfplumber, indexed by `(page, index_on_page)`, and `doc.add_picture()` from the in-memory PNG bytes
- `backend/app/state/models.py` — add `record_extracted_at: datetime | None` and `record_extractor_version: int | None` fields to `ReleaseNotesState`
- `backend/requirements.txt` — add `anthropic` (Claude SDK)
- `.env.example` — add `ANTHROPIC_API_KEY` placeholder
- `config/pipeline.json` — add `claude.model` (default `claude-opus-4-6`), `claude.extractor_version` (default `1`), `claude.max_retries`, `claude.timeout_s`

### Tool-use schemas (final draft)

We use Claude's tool-use feature instead of free-form JSON. Claude is constrained to call our tool with arguments matching the JSON schema. The "tool" doesn't actually execute anything — we just collect the arguments.

**Decision:** one tool only, called once per AM item. Document-level metadata (title, release date) is dropped — we already have version from the filename and product name from config, and the PDF title is just `f"{version} {product}"` anyway.

**Tool: `save_release_note_item`** — called once per AM item, in document order.

| Field | Type | Required | Notes |
|---|---|---|---|
| `section` | string | yes | Verbatim section name from PDF. Items in the same section repeat this value. |
| `am_card` | string | yes | AM number, regex `^AM\d{2,5}$`. Skip items without AM cards — never invent. |
| `customers` | list[string] | yes (can be empty) | List of customer codes (FFT, SWR, PLM, HAL, ETH, ICL, JBU, VKG, …). Empty list if none. An item can belong to multiple customers. |
| `title` | string | yes | Title with AM card and customer codes stripped. Single line, no trailing punctuation. |
| `summary` | string | yes | One short sentence (max ~20 words), paraphrase the body. |
| `body` | array | yes (can be empty) | Body content blocks in document reading order. |

Field rename note: `am_card` is the per-item field; `code` is the body-block type for raw machine-formatted text (log snippets, SQL, ACARS messages). They are different things — don't confuse them.

**Body block fields** — see the "Updated tool schema" section above for the full list of 8 block types and their fields. Validation:

- JSON schema enforces shape (the API rejects malformed calls before they reach us)
- Python validates semantics post-call:
  - `am_card` matches the regex
  - body block fields match the type discriminator
  - `image_id` exists in the manifest
- On validation failure, retry once with a feedback message; fail loudly on second failure

### Body block types — classification first, rendering later

Eight types, all classified by Claude. Rendering decisions deferred — the priority is making sure the record captures the right structure.

| Block type | What it represents |
|---|---|
| `paragraph` | Body text |
| `subheading` | Inline label like "Bug Description", "After correction" |
| `image` | Screenshot reference (`image_id` from manifest) |
| `list` | Bulleted or numbered list, items grouped together |
| `table` | Real data table with headers and rows |
| `note` | "Remark:" / "Note:" callout |
| `warning` | "Warning:" / "Caution:" callout |
| `code` | Raw machine-formatted text — log lines, SQL, ACARS / AFTN messages, flight plan / X19 / FPL payloads, JSON, XML, command output |

Render mapping to Flightscape styles is decided in the implementation block, not here. Unsupported render branches fall back to `Body Text`.

### Record schema (Pydantic) — superseded

The block-by-block models below are an earlier draft. **The authoritative model list lives in the "Updated Pydantic model" section further down**, which covers all 8 body block types. Kept here for context only.

```python
class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    image_id: str
    describes: str

class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str

class SubheadingBlock(BaseModel):
    type: Literal["subheading"] = "subheading"
    text: str

BodyBlock = Annotated[
    ParagraphBlock | SubheadingBlock | ImageBlock,
    Field(discriminator="type"),
]

class ReleaseNoteItem(BaseModel):
    section: str
    am_card: str
    customers: list[str] = Field(default_factory=list)
    title: str
    summary: str
    body: list[BodyBlock] = Field(default_factory=list)

class ReleaseNoteRecord(BaseModel):
    version: str
    extracted_at: datetime
    extractor: str
    extractor_version: int
    source_pdf_path: str
    source_pdf_hash: str
    source_pdf_pages: int
    items: list[ReleaseNoteItem] = Field(default_factory=list)

class ReleaseNotesIndex(BaseModel):
    product_id: str
    schema_version: int = 1
    updated_at: datetime
    release_notes: dict[str, ReleaseNoteRecord] = Field(default_factory=dict)
```

Note: the items are flat at record level — `section` lives on each item rather than as a separate `sections` array. Walking by section is `groupby(items, key=lambda i: i.section)`. Simpler, fewer ways to mismatch sections vs items.

### DOCX render step (post-Claude)

The new emitter is roughly:

```python
def render_record_to_docx(record, template_path, output_path, product_name):
    doc = Document(template_path)
    patch_cover_page(doc, ...)         # KEEP — already written
    clean_cover_textboxes(doc)          # KEEP — already written
    strip_template_body(doc)            # KEEP — already written
    mark_toc_dirty(doc)                 # KEEP — already written

    # Group items by section, preserving first-seen order
    sections_in_order = []
    items_by_section = {}
    for item in record.items:
        if item.section not in items_by_section:
            sections_in_order.append(item.section)
            items_by_section[item.section] = []
        items_by_section[item.section].append(item)

    # Top-level title
    add_styled_paragraph(doc, f"{record.version} {product_name}", "Heading 1")

    # Render
    for section_name in sections_in_order:
        add_styled_paragraph(doc, section_name, "Heading 1")
        for item in items_by_section[section_name]:
            heading = format_item_heading(item)  # "AM3394: [FFT] Security improvements"
            add_styled_paragraph(doc, heading, "Heading 2")
            if item.summary:
                add_styled_paragraph(doc, item.summary, "Body Text")
            for block in item.body:
                if isinstance(block, ParagraphBlock):
                    add_styled_paragraph(doc, block.text, "Body Text")
                elif isinstance(block, SubheadingBlock):
                    add_bold_body_paragraph(doc, block.text)
                elif isinstance(block, ImageBlock):
                    img_bytes = lookup_image(record.source_pdf_path, block.page)
                    if img_bytes:
                        doc.add_picture(io.BytesIO(img_bytes), width=Inches(5.5))

    doc.save(output_path)
```

That's the entire body emitter — about 30 lines. **Everything we wrote in the current `test_docx_conversion.py` for fast/hybrid filtering, OCR-noise dropping, page-chrome detection, heading-level normalization, AM-item promotion, list emission, table emission, and Cyberjet-logo filtering gets DELETED.** The Claude record already has clean structured data; we're just walking it.

Cover-page handling (the four `KEEP —` functions) and the Flightscape template prep stay — those are about the template, not the PDF.

### Image lookup

`lookup_image(pdf_path, page_number)` opens the PDF with pdfplumber, navigates to the requested page, returns the first image's bytes (or `None` if the page has no images).

If a page has multiple images and Claude is referencing the second one, we add an `index_on_page` field to `ImageBlock` and have Claude fill it. v1: assume one image per (page, item-position) and let Claude order images via the body block sequence. If we hit ambiguity in real PDFs, add the index.

### Caching

Two layers, both in `docs_example/conversion_prototype/.cache/`:

- `claude/<sha256>.json` — the raw Claude tool-call results, keyed by PDF hash. Hashing the PDF means re-running on a different PDF reuses cached extractions correctly, and re-running on a re-uploaded PDF triggers re-extraction automatically.
- `claude/.last_run.json` — last successful run metadata for debugging

Cache is invalidated when `--no-cache` is passed or when the cached entry's `extractor_version` is older than the current `config/pipeline.json` value.

### State model integration

Two new fields on `ReleaseNotesState`:

- `record_extracted_at: datetime | None` — when Claude last ran
- `record_extractor_version: int | None` — which extractor version produced the current record

The record itself lives in `state/release_notes_items/<product>.json`, NOT on the patch tracker. The patch tracker just remembers "yes, we have a record for this version, here's how fresh it is."

The orchestrator's docs pass after Unit 4.5:

```
for each patch in tracker:
    if release_notes.status == "not_started":
        fetch_release_notes(patch)   # Unit 3 — Zendesk download

    if release_notes.status == "downloaded" and is_record_stale(patch):
        extract_release_note_record(patch)   # Unit 4.5 — Claude API call
```

`is_record_stale(patch)` returns true when `record_extracted_at is None` OR `record_extractor_version < CURRENT_EXTRACTOR_VERSION`.

DOCX rendering is decoupled from extraction. Extraction runs during scan; rendering is on-demand (CLI for now, API endpoint or approve flow later).

### Cost estimate

- **8.1.12.0 (4 pages, ~12 KB JSON output):** ~$0.02–0.04 per run
- **8.0.18.1 (32 pages, ~30 KB JSON output):** ~$0.15–0.30 per run

At ~30 release notes per month for the whole CAE program: <$10/month for the entire docs pipeline. Trivial.

Caching means re-renders of the same PDF cost zero.

## What we skip until later

- **Frontend review/edit UI** for records — Unit 9 territory (review-before-approve gate)
- **Audit log of edits** in the `review` block of the record — schema reserves the field, implementation deferred
- **Multi-page screenshot anchoring** (where one logical screenshot spans two PDF pages) — investigate when we hit a real example
- **Switching to source `.docx` from Cyberjet** — when CJ delivers source files, replace `extract_release_note(pdf)` with `parse_source_docx(docx)`. Same record schema, same downstream. The architecture isolates the change.

## Block breakdown

Unit 4.5 splits into 5 blocks. Blocks 1, 2, 3 are independent and can run in parallel. Block 4 depends on 1+2+3. Block 5 depends on 4.

### Block 1 — Image extractor
- New module: `backend/app/integrations/pdf/image_extractor.py`
- Library: pypdfium2 (BSD, original image bytes, already in venv)
- Walks every PDF page, extracts embedded images as PNG bytes
- Computes bbox, dimensions, sha256, sorts by reading order, assigns IDs (`p{page}_img{index}`)
- Flags chrome images (Cyberjet logo, top-band) — saved but excluded from Claude's manifest
- Writes PNGs + `manifest.json` to `<pdf_dir>/images/`
- Idempotent: if manifest hash matches PDF hash, skip
- Tested with a fixture PDF

### Block 2 — Record models + store
- `backend/app/state/release_notes_models.py` — Pydantic models for `ReleaseNoteRecord`, `ReleaseNoteItem`, all 8 body block types, `ReleaseNotesIndex`, `ImageManifest`
- `backend/app/state/release_notes_store.py` — `load_release_notes`, `save_release_notes`, `get_record`, `upsert_record`. Mirrors `state/manager.py`, atomic writes
- Pure data layer, unit tests

### Block 3 — Claude extractor
- `backend/app/integrations/claude/__init__.py`
- `backend/app/integrations/claude/client.py` — Anthropic SDK wrapper, auth, retries, timeouts
- `backend/app/integrations/claude/extractor.py` — `extract_release_note(pdf_path, manifest) → ReleaseNoteRecord`
  - Builds the tool-use schema for `save_release_note_item` (covers all 8 body block types)
  - Builds the prompt with the rules for sections, AM codes, customer codes, image IDs, list/table grouping, callouts, code blocks
  - Sends PDF as document content + manifest text as user message
  - Collects tool calls, validates each (regex on `am_card`, `image_id` exists in manifest, etc.)
  - Returns a `ReleaseNoteRecord`. **Pure function — does not save anywhere.**
- Tested with a recorded fixture response (no live API in CI). Live API smoke test is manual.

### Block 4 — Wire into `test_docx_conversion.py`
- New `--mode claude` branch in the script
- Flow: extract images (block 1) → call Claude (block 3) → save record via store (block 2) → render DOCX
- New ~30-line walker replaces ~600 lines of fast/hybrid filters
- Image rendering: load `<pdf_dir>/images/<image_id>.png` from disk, no PDF re-parse
- Render branches for the 8 block types — minimum viable for v1 (paragraph / subheading / image fully implemented; list / table / note / warning / code can fall back to `Body Text` initially and get proper styles later)
- Manual eyeball test against 8.1.12.0, 8.0.16.1, 8.0.18.1

### Block 5 — Orchestrator integration
- Add `record_extracted_at` and `record_extractor_version` fields to `ReleaseNotesState` in `backend/app/state/models.py`
- Add the extraction step to the docs pass in `backend/app/services/orchestrator.py`, wrapped in `lifecycle.run_cell` with `step_name="extract"`
- Triggers when `release_notes.status == "downloaded"` and `is_record_stale(patch)` returns true
- Fixture-based orchestrator test
- Update `config/pipeline.json` with `claude.model`, `claude.extractor_version`, `claude.max_retries`, `claude.timeout_s`

## Decisions

- **Multiple images per page:** handled by the `p{page}_img{index}` ID convention. Index is 1-based reading order (top-to-bottom, left-to-right). No body-block ambiguity — Claude always references a specific image by ID.
- **Validation failures we handle ourselves** (Claude-specific only): tool-call schema violation, unknown `image_id`, empty result with no tool calls. Retry once with a feedback message; fail loudly on second failure. `lifecycle.run_cell` catches the exception, marks `last_run.state = failed`, next scan retries.
- **Network / rate-limit errors** (429, 5xx, timeouts) are handled by the Anthropic SDK's built-in retry with exponential backoff. We don't wrap them.
- **Claude model:** default `claude-opus-4-6`. Configurable in `config/pipeline.json` under `claude.model`. A/B against sonnet possible later if cost matters.
- **API key:** `ANTHROPIC_API_KEY` in `.env`. Same pattern as `JIRA_API_TOKEN_NO_SCOPES` and `ZENDESK_PASSWORD`. Alex adds it manually; never committed.
- **State file name and location:** `state/release_notes_items/<product>.json`. Separate from `state/patches/` to avoid confusion with patch binaries state.
- **Item ID field:** `am_card` (renamed from `code` to avoid clash with the `code` body-block type which represents raw machine-formatted text like ACARS messages / SQL / logs).
- **Customers field:** `customers: list[str]` (not a single string — one AM item can belong to multiple customers).

## Verdict

Manual chat validation on `8.0.18.1 - Release Notes.pdf` produced output that fast and hybrid couldn't match after a day of iteration. The structural extraction problem is solved; what's left is plumbing (Anthropic SDK call, record store, simplified DOCX walker).

**Recommendation:** ship Unit 4.5 as the next iteration. If the implementation matches the chat validation, Unit 5 unblocks immediately and the docs pipeline moves to integration.
