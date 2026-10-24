# AI Contract Assistant

A small prototype that lets users browse contracts and ask questions about them:
a contract list, a RAG assistant that answers from the contract PDFs with citations
(contract, clause and page), an MCP server whose tools the LLM chooses to call, and an
Angular frontend split into a host and a remote with Native Federation.

> **Status:** steps 1-5 of 7 done: the whole backend (PDF ingestion, contracts API, MCP server, retrieval and the AI assistant). The Angular frontend is next.
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

The first `ingest` run downloads the local embedding model (about 80 MB) into `~/.cache/chroma`
(on Windows `C:\Users\<you>\.cache\chroma`). Later runs reuse it. **Stop the MCP server before re-running
`ingest`**, because Windows locks the index files while the server has them open.

**MCP server.** Start it in a second terminal from the `backend` folder, with the virtual environment active:

```powershell
python -m mcp_server              # serves http://127.0.0.1:8001/mcp
python -m scripts.check_mcp       # optional, in a third terminal: lists the tools and calls each one
```

**The assistant.** Configure the model once:

```powershell
copy .env.example .env            # macOS/Linux: cp .env.example .env
notepad .env                      # set LLM_API_KEY=sk-...   (leave it empty for mock mode)
```

With the MCP server running, ask questions from the command line, or call `POST /chat` (restart `uvicorn` after
editing `.env`):

```powershell
python -m scripts.ask "Which contracts expire in the next 30 days?"
python -m scripts.ask --demo      # the six demo questions; add --mock to force mock mode
```

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
   - **Embeds every chunk into a local vector index** (`backend/data/chroma/`); see [Clause retrieval](#clause-retrieval).
   - **Outputs** also include `backend/data/extracted/<id>.md` (exactly what the model will see) and
     `backend/data/chunks.json`.

Everything under `backend/data/` is generated and gitignored.

## API (so far)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok", "database_ready": true}` |
| GET | `/contracts` | All contracts, soonest expiration first: id, title, counterparty, type, dates, status, days until expiration, `pdf_url` |
| GET | `/contracts/{id}` | One contract (404 if unknown) |
| GET | `/contracts/{id}/pdf` | The original PDF, served inline so `.../pdf#page=3` opens on page 3 |
| POST | `/chat` | Ask the assistant: `{"message": "...", "history": [...]}` returns the answer, citations, tool-call trace and mode |

`/health` also reports `assistant_mode` (`openai` or `mock`) and the model, for the UI badge. Status is recalculated from today's date on every request, so a contract that passes its expiration date shows
as "Expired" without re-running setup. If setup hasn't been run, the API answers `503` with the commands to run.
CORS allows the Angular dev servers (`http://localhost:4200` and `:4201`); override with `CORS_ORIGINS`.

## MCP server

`backend/mcp_server/` is a standalone [MCP](https://modelcontextprotocol.io) server built with the official
Python SDK (`mcp`, v1 line), served over **Streamable HTTP** at `http://127.0.0.1:8001/mcp`. It runs as its own
process, so the assistant talks to it over real MCP, and so can any other MCP client.

| Tool | Input | Returns |
|---|---|---|
| `search_contracts` | `query` (words matched against title, counterparty and type), `status` (`Active` / `Expired`), both optional | Matching contracts with dates, status and days until expiration |
| `get_upcoming_expirations` | `days` (0-3650) | Active contracts expiring between today and today + `days`, soonest first, plus the date window used |
| `search_contract_clauses` | `query`, optional `contract_id`, `group_by_contract`, `top_k` | The most relevant clauses with their text, a ready-made citation (contract, clause, pages) and a similarity score |

- **Tool descriptions are written as documentation**: what the tool does, when to use it, and what it returns.
  They're what the LLM reads when deciding which tool to call.
- **Date arithmetic happens in the tool**, never in the prompt or the model.
- **Results are structured** (JSON matching each tool's output schema) and inputs are validated, so `days=-5` is
  rejected with a clear error.
- **Each tool call is logged** in the server console, which makes it easy to see when the assistant used a tool.

**Inspecting it with the official MCP Inspector** (needs Node.js):

```powershell
npx @modelcontextprotocol/inspector
```

In the page that opens, choose **Transport: Streamable HTTP**, enter `http://127.0.0.1:8001/mcp`, click
**Connect**, then **Tools → List Tools** and run either tool.

## Clause retrieval

This is the retrieval half of RAG. The assistant (next step) calls `search_contract_clauses` and answers only from
the clauses it returns.

- **Index.** [Chroma](https://www.trychroma.com/) running locally, cosine similarity, one document per clause chunk.
  What gets embedded is the contract title and clause heading followed by the clause text, so "termination in the
  Helix contract" matches on both the contract and the topic.
- **Embeddings.** `all-MiniLM-L6-v2`, Chroma's default model, runs on your machine through ONNX Runtime. No API key
  is needed, so retrieval also works in mock mode. Telemetry is switched off.
- **Filters.** `contract_id` searches inside one contract. `group_by_contract=true` searches each contract separately
  and returns its best clauses. That's how "which contracts renew automatically?" checks all five contracts instead
  of returning the top five chunks from two of them.
- **"Not enough evidence".** Matches scoring below 0.25 (`RETRIEVAL_MIN_SCORE`) are dropped. If nothing passes, the
  tool returns the closest three, flagged `weak_matches_only` with a note, so the model can rephrase or say the
  contracts don't cover the question instead of guessing.

How it ranks the demo questions:

| Query | Top result | Score |
|---|---|---|
| termination conditions (C-003) | Master Supply Agreement, clause 8 Termination, pp. 2-3 | 0.50 |
| automatic renewal (per contract) | each contract's Term / Term and Renewal / Duration clause | 0.26-0.56 |
| termination conditions (C-004, the NDA) | clause 6 Duration only; the NDA has no termination clause | 0.26 |
| parental leave policy | nothing relevant, so weak matches only | < 0.25 |

Known limitation: MiniLM is small, so very casual phrasing ("how do we get out of the deal early?") scores low. The
tool description asks the model to search in contract language ("early termination"), which fixes this in practice.
A larger embedding model would be a drop-in improvement.

## The assistant: how it uses RAG and the MCP tools

`backend/app/agent.py` runs one loop per question:

1. **Discover the tools.** Connect to the MCP server over Streamable HTTP and call `list_tools`. Each tool's name,
   description and JSON schema become a function definition for the model.
2. **Ask the model.** Send the system prompt, any earlier turns and the question, plus the tool definitions. The prompt
   contains no contract facts, only rules: use `search_contract_clauses` for anything a contract says, `search_contracts`
   for which contracts exist, `get_upcoming_expirations` for date windows; never compute dates; cite sources; say there's
   not enough evidence instead of guessing.
3. **Run the tools the model picks.** For every tool call, the backend executes it through MCP and returns the JSON
   result to the model. Repeat until the model answers in text, for at most `AGENT_MAX_ROUNDS` (default 5).
   Multi-step questions work naturally. For "of the contracts expiring in the next 90 days, which renew automatically?",
   the model calls `get_upcoming_expirations(90)`, then `search_contract_clauses` for each result.
4. **Check the citations.** The model cites `[C-003:8]` for a clause or `[C-001]` for contract data. The backend keeps
   only ids that appeared in this conversation's tool results, renumbers them `[1]`, `[2]`... and attaches the label, a
   quote and a PDF link to the cited page (`/contracts/C-003/pdf#page=2`). Invented ids are removed and reported in
   `warnings`. `grounded: false` means the answer cites nothing.

The response also carries the **tool-call trace** (tool, arguments, result summary, duration), so the UI can show which
tools the model chose. The MCP server logs every call on its console too.

**Model.** Any OpenAI-compatible Chat Completions endpoint works; it's all configuration in `.env`:

| Setting | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | (empty) | API key. Empty means mock mode. |
| `LLM_MODEL` | `gpt-6-luna` | OpenAI's cheapest current model. It supports tool calling in Chat Completions when reasoning is off. |
| `LLM_REASONING_EFFORT` | `none` | Sent as `reasoning_effort`. Leave empty for providers that don't support it. |
| `LLM_BASE_URL` | OpenAI | e.g. an Azure / Microsoft Foundry v1 endpoint, or Ollama's `http://localhost:11434/v1` |
| `LLM_MODE` | `auto` | `auto` (real model if a key is set), `openai`, or `mock` |

The larger GPT-6 models (`gpt-6.1-sol`, `gpt-6-astra`) only support tool calling through OpenAI's Responses API, so
they aren't supported by this Chat Completions client. `gpt-5.4-mini` is a drop-in alternative. Provider errors
(bad key, quota, unsupported model) come back as `502` with the provider's message; an unreachable MCP server gives `503`.

**Mock mode** (`backend/app/mock_llm.py`) is used when no API key is set. It replaces only the model: keyword rules pick
the same tools a model would (including multi-step plans) and the answer quotes the retrieved clauses. The MCP calls,
retrieval and citation checking are all real. Answers are labelled as mock, and `/health` reports
`assistant_mode: "mock"`. It's meant for trying the UI and API without a key, not as a replacement for the model.

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
    queries.py                contract search and expiration look-ups (used by the MCP tools)
    retrieval.py              Chroma vector index: build, semantic clause search, evidence threshold
    mcp_client.py             MCP client: connect, list tools, call tools
    agent.py                  the assistant: tool-calling loop, system prompt, citation checking
    llm.py                    OpenAI-compatible Chat Completions client
    mock_llm.py               rule-based stand-in used in mock mode
    routers/
      contracts.py            /contracts endpoints and PDF serving
      chat.py                 POST /chat
    ingestion/
      pdf_extract.py          PDF -> per-page Markdown, header/footer removal
      chunking.py             clause chunks with page ranges and citations
  mcp_server/
    server.py                 MCP server and tool definitions
  sample_contracts/           sample-data generator only (not used by ingestion)
    templates/                contract templates (plain text)
    builder.py                templates + dates -> contract documents
    pdf_writer.py             contract documents -> PDF (fpdf2)
  scripts/
    generate_contracts.py     step: create the sample PDFs
    ingest.py                 step: load SQLite, extract and chunk the PDFs, build the index
    check_mcp.py              smoke test for the MCP server
    ask.py                    ask the assistant from the command line (--demo, --mock)
  .env.example                settings template (copy to .env)
  requirements.txt
```

## Notes

- `mcp` is kept on the v1 line (`>=1.30,<2`). Version 2 (August 2026) renamed the main classes, and most
  examples and tooling still target v1.
- `pymupdf4llm` is pinned to `1.28.2`. It requires the exact matching PyMuPDF version, and the unpinned
  latest release (`2.0`) installs an empty package.
- PyMuPDF / pymupdf4llm are AGPL-3.0 licensed. That's fine for this prototype; a commercial product would
  need a licence or a permissive extractor such as `pypdf`.
- Only text-based PDFs are supported. Scanned contracts would need OCR (future work).
