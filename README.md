# Personal-Agent

```text
                         _________________________
                        |                         |
                        |   A WORK IN PROGRESS    |
                        |_________________________|
                                  \
                                   \
                                    O
                                   /|\
                                   / \

                 /
        /\      /  \      /\
       /  \____/    \____/  \        Personal-Agent is alive,
      /                        \      slightly chaotic,
     /   files, images, text,   \     and getting smarter every run.
    /   search, memory, agents   \
   /______________________________\
```

> A personal file intelligence agent that can ingest files, extract useful context, store metadata, search across multiple retrieval layers, and prepare compact answers for an LLM-powered query agent.

---

## What is this project?

**Personal-Agnet** is a local-first personal agent project designed to help you search, understand, and reason over your own files.

The goal is simple:

```text
Give the agent a messy pile of files
            ↓
Extract metadata, text, OCR, image understanding, tags, and entities
            ↓
Store everything in SQLite and ChromaDB
            ↓
Search with exact, semantic, metadata, tag/entity, and visual retrieval
            ↓
Return useful, explainable answers with file links and matched reasons
```

In other words, this repo is slowly becoming your own searchable memory layer for personal files, documents, images, and future automations.

---

## Project status

```text
╔══════════════════════════════════════════════════════╗
║                  CURRENT STATUS                     ║
╠══════════════════════════════════════════════════════╣
║  MVP exists                                         ║
║  File processing works                              ║
║  SQLite storage exists                              ║
║  Chroma semantic search exists                      ║
║  Image OCR + visual metadata flow exists            ║
║  Query agent retrieval is being improved            ║
║  Ranking, merging, and answer packing are evolving  ║
╚══════════════════════════════════════════════════════╝
```

This is not yet a finished production assistant. It is a working personal-agent foundation with active improvements around search accuracy, visual understanding, explainability, and LLM-ready context generation.

---

## What the project has so far

### Core capabilities

| Area | What exists today | Status |
|---|---|---:|
| Google Drive ingestion | Pulls files from a configured Drive folder | ✅ Working |
| Local file processing | Processes supported files into local storage | ✅ Working |
| SQLite metadata DB | Stores file records, metadata, content, tags, entities, and timestamps | ✅ Working |
| PDF text extraction | Extracts text from PDFs using PyMuPDF / `fitz` | ✅ Added |
| DOCX text extraction | Extracts paragraph text from Word documents | ✅ Added |
| Image OCR | Extracts visible text from images using OCR | ✅ Working |
| Image metadata | Extracts EXIF capture time when available | ✅ Working |
| Visual summaries | Creates image-focused descriptions for search and reasoning | ✅ In progress |
| Tag inference | Infers tags like baby, identity document, receipt, screenshot, etc. | ✅ In progress |
| Entity inference | Extracts searchable entities from file content and metadata | ✅ In progress |
| ChromaDB | Stores embeddings for semantic retrieval | ✅ Working |
| Sentence transformers | Uses `all-MiniLM-L6-v2` embeddings | ✅ Working |
| Query agent | Searches and answers over indexed data | ✅ In progress |
| Search explainability | Shows why a file matched a query | ✅ Added / improving |
| Hard reset script | Clears DB / Chroma for clean re-indexing | ✅ Planned / partially added |

---

## Current architecture

```text
┌────────────────────┐
│   Google Drive      │
│  source folder(s)   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  File ingestion     │
│  / sync script      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────────────────────┐
│        File processing layer        │
├────────────────────────────────────┤
│ PDF text extraction                 │
│ DOCX text extraction                │
│ Image OCR                           │
│ EXIF metadata extraction            │
│ Caption / visual summary extraction │
│ Tag inference                       │
│ Entity inference                    │
└─────────┬──────────────────────────┘
          │
          ├──────────────────────────────┐
          ▼                              ▼
┌────────────────────┐          ┌────────────────────┐
│      SQLite         │          │      ChromaDB       │
│ metadata + content  │          │ semantic embeddings │
└─────────┬──────────┘          └─────────┬──────────┘
          │                               │
          └──────────────┬────────────────┘
                         ▼
              ┌────────────────────┐
              │   Search service    │
              │ exact / metadata /  │
              │ tags / entities /   │
              │ semantic / visual   │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │    Query agent      │
              │ ranked results +    │
              │ answer context      │
              └────────────────────┘
```

---

## Main project components

> File names may change as the project evolves. This table describes the logical structure of the current project.

| Component | Purpose |
|---|---|
| `process_files.py` | Pulls files, processes them, and stores results |
| `query_agent.py` | Handles user queries and retrieval flow |
| `search_service.py` | Performs SQLite, metadata, tag/entity, and semantic search |
| `chroma_config.py` | Creates and manages ChromaDB client / collection |
| `db.py` / database helpers | Creates tables and writes file metadata/content |
| `extract_text_from_pdf()` | Extracts text from PDF files |
| `extract_text_from_docx()` | Extracts text from DOCX files |
| `extract_image_metadata_and_caption()` | Extracts image metadata, OCR, caption, visual summary, and EXIF date |
| `infer_tags()` | Infers useful tags from file name, source folder, OCR, captions, summaries, and visual JSON |
| `infer_entities()` | Extracts useful searchable entities from file content |
| `build_chunk_records()` | Builds chunks that can be embedded into ChromaDB |
| Reset script | Cleans SQLite / Chroma for a fresh rebuild |

---

## Retrieval model

The search system is moving toward a unified retrieval model where every source returns the same result shape before merging and ranking.

### Retrieval sources

| Retrieval type | Example use case | Why it matters |
|---|---|---|
| Exact file-name search | `show me Liron CV` | Finds obvious direct matches fast |
| SQLite text search | Search extracted PDF / DOCX text | Good for documents and OCR text |
| Metadata search | Search by file type, source folder, dates | Useful for filtering and timelines |
| Tag search | Search for `baby`, `receipt`, `id`, `screenshot` | Gives the agent human-like categories |
| Entity search | Search people, vendors, tools, document types | Makes search more structured |
| Chroma semantic search | Search by meaning, not just keywords | Helps when wording is different |
| Visual summary search | Search what appears in images | Needed for image-heavy memories |
| OCR search | Search text visible inside images | Critical for screenshots and scanned docs |

---

## Unified result shape

The goal is for every retrieval path to return results in a shared format.

```text
┌────────────────────────────────────────────┐
│ Unified Search Result                      │
├────────────────────────────────────────────┤
│ file_id                                    │
│ file_name                                  │
│ drive_file_id                              │
│ drive_web_link                             │
│ mime_type                                  │
│ source_folder                              │
│ score                                      │
│ source                                     │
│ match_type                                 │
│ matched_field                              │
│ matched_value                              │
│ matched_reason                            │
│ extracted_text                             │
│ ocr_text                                   │
│ image_caption                              │
│ visual_summary                             │
│ exif_capture_time                          │
│ drive_created_time                         │
│ drive_modified_time                        │
└────────────────────────────────────────────┘
```

This makes it easier to merge search results from SQLite, exact search, metadata search, tag/entity search, OCR search, visual search, and Chroma semantic retrieval.

---

## Ranking approach

The ranking system is being improved to prefer results that are likely to be truly relevant.

### Current / planned ranking signals

| Signal | Purpose |
|---|---|
| Exact file-name match | Strong boost for direct file requests |
| Query appears in extracted text | Good signal for documents |
| Query appears in OCR text | Good signal for screenshots/images |
| Tag match | Strong when the user searches by category |
| Entity match | Strong when the query maps to a known person/object/vendor/type |
| Semantic distance | Captures meaning beyond exact wording |
| Visual summary match | Helps image search feel smart |
| Date logic | Supports first/latest/oldest/recent image questions |
| Source folder | Helps narrow intent when folders are meaningful |

---

## Date-based ranking

For questions like:

```text
show me the first baby picture
show me the latest image
find my oldest screenshot
```

The ranking should prefer dates in this order:

| Priority | Date source | Why |
|---:|---|---|
| 1 | EXIF capture time | Closest to when the photo was actually taken |
| 2 | Local / file created time | Useful fallback |
| 3 | Google Drive created time | Useful but may reflect upload time |
| 4 | Google Drive modified time | Last fallback, not always capture-related |

```text
EXIF first.
Drive modified last.
Because upload time lies.
Photos know things.
```

---

## Answer context packer

The query agent should convert top-ranked results into compact, LLM-ready context.

The context pack should include:

| Field | Why it helps the LLM |
|---|---|
| File name | Gives identity and user-facing reference |
| Drive link | Lets the user open the original file |
| Source folder | Helps explain where it came from |
| Dates | Supports timeline reasoning |
| Extracted text | Main content for docs/PDFs |
| OCR text | Text found in screenshots/images |
| Visual summary | Lets the model reason about image content |
| Image caption | Short visual description |
| Matched reason | Explains why this file was selected |
| Match type | Shows whether it was exact, semantic, tag, entity, OCR, etc. |
| Score | Helps choose strongest results |

Example context pack:

```text
[Result 1]
File: 20260415_131647.jpg
Source: images
Date: 2026-04-15 13:16:47
Match type: visual_summary
Matched reason: Visual summary mentions a baby sitting indoors.
Drive link: https://drive.google.com/...
OCR: None
Visual summary: A baby is sitting on a couch near a table...
```

---

## Why explainability matters

One of the project goals is not only to return files, but to explain why they were returned.

Bad result:

```text
baby.jpg score: 0.72
```

Better result:

```text
baby.jpg score: 0.72
Matched because:
- tag matched: baby
- visual summary mentioned: infant sitting indoors
- OCR did not contribute
- semantic search distance: 0.31
```

This makes debugging search quality much easier.

---

## Supported file types

| File type | Current support |
|---|---:|
| Images | ✅ OCR, EXIF, caption / visual summary |
| PDFs | ✅ Text extraction |
| DOCX | ✅ Text extraction |
| Text files | 🟡 Planned / simple support |
| Videos | ❌ Not yet supported |
| Audio | ❌ Not yet supported |
| Spreadsheets | 🟡 Future support |

---

## Local data stores

| Store | Purpose |
|---|---|
| SQLite | Structured metadata, file records, extracted content, tags, entities |
| ChromaDB | Vector embeddings for semantic search |
| Local file cache | Temporary or persistent file downloads from Drive |

---

## Example queries the agent should support

```text
show me Liron CV
find pictures with a baby
show me the latest image
show me the first baby photo
find screenshots with login errors
show files from the images folder
find documents mentioning passport
what files did we process recently?
why did this file match my query?
```

---

## Development philosophy

```text
       Search should be useful.
       Results should be explainable.
       Ranking should be debuggable.
       The agent should say why.
       The database should stay clean.
       The code should survive future-you.
```

Also:

```text
       If it matched because of OCR, say OCR.
       If it matched because of tags, say tags.
       If it matched because embeddings got creative,
       definitely say that too.
```

---

## Suggested setup

> Adjust this section based on your actual environment and dependency files.

```bash
# Clone the repo
git clone https://github.com/perzibel/Personal-Agent.git
cd Personal-Agent

# Create a virtual environment
python -m venv .venv

# Activate it on Windows
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Optional but recommended:

```bash
# Set Hugging Face token for better rate limits
set HF_TOKEN=your_token_here
```

---

## Running the processor

```bash
python process_files.py
```

Expected outcome:

```text
Processing file: example.pdf
Processed successfully

Processing file: image.jpg
Extracted EXIF
Extracted OCR
Generated visual summary
Inserted into SQLite
Inserted chunks into Chroma
Processed successfully
```

---

## Running search tests

Example test script:

```python
from pathlib import Path
import sqlite3
from app.search_service import search_sqlite_by_query

base_dir = Path(__file__).resolve().parent.parent
db_path = base_dir / "data" / "agent_memory.db"

conn = sqlite3.connect(db_path)
try:
    results = search_sqlite_by_query(
        conn=conn,
        query="baby",
        limit=10,
    )

    for item in results:
        print(item["file_name"], item["score"], item.get("matched_reason"))
finally:
    conn.close()
```

---

## Debugging search quality

When a result feels wrong, inspect:

| Check | What to look for |
|---|---|
| `matched_reason` | Why did it match? |
| `matched_field` | Was it file name, OCR, tag, entity, visual summary, or embedding? |
| `score` | Was the score too high? |
| Chroma distance | Was semantic search too loose? |
| Tags | Did `infer_tags()` over-tag the file? |
| OCR | Did OCR extract noisy text? |
| Visual summary | Did the caption hallucinate or over-generalize? |

Tiny debugging goblin:

```text
      ,      ,
     /(.-""-.)\
 |\  \/      \/  /|
 | \ / =.  .= \ / |
 \( \   o\/o   / )/
  \_, '-/  \-' ,_/
    /   \__/   \
    \ \__/\__/ /
  ___\ \|--|/ /___
 /`    \      /    `\
        '----'

It found a weird match.
Check the matched_reason.
```

---

## Current next steps

### Short-term roadmap

| Step | Task | Goal |
|---:|---|---|
| 1 | Build unified retrieval response model | Normalize SQLite, exact, tag/entity, metadata, OCR/text, and Chroma results into the same shape |
| 2 | Merge and rank results | Combine all retrieval sources into one ranked list |
| 3 | Add stronger date-based ranking | Support first/latest/oldest image and document queries |
| 4 | Build answer context packer | Convert top results into compact LLM-ready context |
| 5 | Improve visual retrieval | Search visual summaries and vision entities more accurately |
| 6 | Improve matched reasons | Make every result explain why it was returned |
| 7 | Add tests | Validate ranking, retrieval merging, date logic, and context packing |
| 8 | Add reset script | Clean SQLite, Chroma, and local cache safely |
| 9 | Add video support | Extract frames, metadata, transcript, or summaries from videos |
| 10 | Add better docs | Keep README, architecture notes, and dev flow updated |

---

## Recommended tests to add

| Test file | What it should validate |
|---|---|
| `test_unified_result_model.py` | Every retrieval source returns the same result schema |
| `test_merge_rank_results.py` | Exact, metadata, tag, entity, OCR, visual, and semantic results merge correctly |
| `test_date_ranking.py` | EXIF is preferred over created/modified dates |
| `test_answer_context_packer.py` | Top results become compact LLM-ready context |
| `test_search_explainability.py` | Every result includes a useful matched reason |
| `test_visual_retrieval.py` | Visual summaries and image tags are searchable |
| `test_reset_script.py` | Reset script safely clears DB and Chroma |

---

## Known limitations

| Limitation | Impact |
|---|---|
| Video files are not supported yet | `.mp4` files currently fail processing |
| Semantic distance may be too loose | Some irrelevant files can appear |
| Tag inference can over-match | A file may get a tag from weak text clues |
| OCR can be noisy | Screenshots/images may create weird matches |
| Visual summaries need tuning | Image search depends heavily on summary quality |
| Ranking is still evolving | Multiple retrieval sources need smarter merging |
| No full production UI yet | Mostly script / CLI driven for now |

---

## Future ideas

```text
┌───────────────────────────────────────────┐
│              FUTURE POWERS                │
├───────────────────────────────────────────┤
│ Web UI for search                         │
│ Better file preview cards                 │
│ User feedback loop for bad matches        │
│ Auto re-ranking based on feedback         │
│ Video frame extraction                    │
│ Audio transcription                       │
│ Spreadsheet extraction                    │
│ Local LLM support                         │
│ Scheduled Drive sync                      │
│ Personal memory API                       │
│ Smart home / life automation integrations │
└───────────────────────────────────────────┘
```

---

## Project vibe

```text
        This repo is not just a search tool.
        It is a tiny librarian with caffeine.

        It reads.
        It squints at images.
        It OCRs screenshots.
        It stores metadata.
        It embeds chunks.
        It sometimes gets confused.
        Then we make it explain itself.
```

---

## Final note

This project is actively being built.

The current focus is retrieval quality:

```text
more accurate search
+ better ranking
+ better visual understanding
+ better explanations
+ compact answer context
= a personal agent that actually feels useful
```

No one knows yet.
