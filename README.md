# AI Contract Assistant

A small prototype that lets users browse contracts and ask questions about them:
a contract list, a RAG assistant that answers from the contract PDFs with citations
(contract, clause and page), an MCP server whose tools the LLM chooses to call, and an
Angular frontend split into a host and a remote with Native Federation.

> **Status:** steps 1-2 of 7 done: sample contract PDFs, the PDF ingestion pipeline, and the contracts API.
> The full run guide, architecture notes and the RAG / MCP explanation will be added as the remaining steps land.

## Setup so far

Requires Python 3.10 or newer.

**Windows (PowerShell)**

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m scripts.generate_contracts
python -m scripts.ingest --show-chunks
uvicorn app.main:app --reload --port 8000
```

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.generate_contracts
python -m scripts.ingest --show-chunks
uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000/docs for the interactive API documentation.

## What the setup commands do

1. **`generate_contracts`** turns the templates in `backend/sample_contracts/templates/` into five
   realistic PDF contracts (3-5 pages each, numbered clauses, a "Confidential" header, a "Page X of Y"
   footer and a signature block) plus `metadata.json` for the contract list. Expiration dates are
   computed relative to the day you run it, so "expiring in the next 30 days" always has an answer.
   All companies and people are fictional.
2. **`ingest`** reads only the PDFs and `metadata.json`, never the templates:
   - **Loads the contract list into SQLite** (`backend/data/contracts.db`), rebuilt from scratch on every run.
   - **PDF to Markdown, page by page**, with [pymupdf4llm](https://pypi.org/project/pymupdf4llm/).
     Its layout analysis tags running headers and footers so they can be dropped. A second, generic
     pass removes any short line that repeats on most pages, in case one slips through.
   - **One chunk per clause.** Sub-clauses (8.1, 8.2...) stay with their clause, and each chunk records
     the pages it spans, e.g. *Master Supply Agreement (C-003), clause 8, pp. 2-3*.
   - **Outputs** go to `backend/data/extracted/<id>.md` (exactly what the model will see) and
     `backend/data/chunks.json`.

Everything under `backend/data/` is generated and gitignored.

## API (so far)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok", "database_ready": true}` |
| GET | `/contracts` | All contracts, soonest expiration first: id, title, counterparty, type, dates, status, days until expiration, `pdf_url` |
| GET | `/contracts/{id}` | One contract (404 if unknown) |
| GET | `/contracts/{id}/pdf` | The original PDF, served inline so `.../pdf#page=3` opens on page 3 |

Status is recalculated from today's date on every request, so a contract that passes its expiration date shows
as "Expired" without re-running setup. If setup hasn't been run, the API answers `503` with the commands to run.
CORS allows the Angular dev servers (`http://localhost:4200` and `:4201`); override with `CORS_ORIGINS`.

## Sample contracts

| ID | Contract | Counterparty | Expires | Built to test |
|---|---|---|---|---|
| C-001 | SaaS Subscription Agreement | Orbis Cloud GmbH | in 20 days | 30-day expirations; auto-renewal |
| C-002 | Office Space Licence Agreement | Castello Immobiliare S.r.l. | in 75 days | 90-day window; no auto-renewal |
| C-003 | Master Supply Agreement | Helix Components S.p.A. | in ~14 months | auto-renewal; termination clause spanning two pages |
| C-004 | Mutual Non-Disclosure Agreement | Brightline Analytics Ltd | in ~2 years | no termination clause, so "insufficient evidence" |
| C-005 | Consulting Services Agreement | Verdi & Partners Consulting S.r.l. | 40 days ago | expired status |

## Project layout (so far)

```
backend/
  app/
    main.py                   FastAPI app: CORS, error handling, routers
    config.py                 file locations and settings
    db.py                     SQLite contract store
    schemas.py                API response models
    routers/
      contracts.py            /contracts endpoints and PDF serving
    ingestion/
      pdf_extract.py          PDF -> per-page Markdown, header/footer removal
      chunking.py             clause chunks with page ranges and citations
  sample_contracts/           sample-data generator only (not used by ingestion)
    templates/                contract templates (plain text)
    builder.py                templates + dates -> contract documents
    pdf_writer.py             contract documents -> PDF (fpdf2)
  scripts/
    generate_contracts.py     step: create the sample PDFs
    ingest.py                 step: load SQLite, extract and chunk the PDFs
  requirements.txt
```

## Notes

- `pymupdf4llm` is pinned to `1.28.2`. It requires the exact matching PyMuPDF version, and the unpinned
  latest release (`2.0`) installs an empty package.
- PyMuPDF / pymupdf4llm are AGPL-3.0 licensed. That's fine for this prototype; a commercial product would
  need a licence or a permissive extractor such as `pypdf`.
- Only text-based PDFs are supported. Scanned contracts would need OCR (future work).
