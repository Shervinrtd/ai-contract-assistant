"""Central configuration: file locations used by the backend and the setup scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Settings come from environment variables, optionally via backend/.env (never committed).
load_dotenv(BACKEND_DIR / ".env")

# Everything generated at setup time lives under DATA_DIR (gitignored).
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data")).resolve()

CONTRACTS_DIR = DATA_DIR / "contracts"          # generated PDFs
METADATA_FILE = CONTRACTS_DIR / "metadata.json"  # list metadata written by the generator
EXTRACTED_DIR = DATA_DIR / "extracted"           # Markdown extracted from each PDF (for inspection)
CHUNKS_FILE = DATA_DIR / "chunks.json"           # clause-level chunks with page ranges
DB_FILE = DATA_DIR / "contracts.db"              # SQLite store for the contract list
CHROMA_DIR = DATA_DIR / "chroma"                 # vector index of clause chunks

# Clause search: hits below this cosine similarity are treated as "no evidence".
# Calibrated for the default all-MiniLM-L6-v2 embeddings on the sample contracts.
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.25"))

# Where the backend reaches the MCP server (127.0.0.1 avoids slow IPv6 "localhost" lookups on Windows).
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

# Frontend origins allowed to call the API (Angular host and remote dev servers).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:4200,http://localhost:4201").split(",")
    if o.strip()
]


def display_path(path: Path) -> str:
    """Path relative to the backend folder when possible (for log messages)."""
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


# ----------------------------------------------------------------- assistant

# Any OpenAI-compatible Chat Completions endpoint can be used: OpenAI (default), Azure / Microsoft
# Foundry, Groq, Ollama... should only need these settings (tested with OpenAI only).
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None          # None = https://api.openai.com/v1
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-6-luna")
# gpt-6-luna supports tool calling in Chat Completions only with reasoning effort "none".
# Set to an empty value for providers that do not accept this parameter.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "none").strip() or None
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# "auto": use the real model when an API key is configured, otherwise mock mode.
# "openai": always use the real model.  "mock": always use the rule-based stand-in.
LLM_MODE = os.getenv("LLM_MODE", "auto").strip().lower()

AGENT_MAX_ROUNDS = int(os.getenv("AGENT_MAX_ROUNDS", "5"))  # model <-> tools round trips per question


def assistant_mode() -> str:
    if LLM_MODE == "mock":
        return "mock"
    if LLM_MODE == "openai" or LLM_API_KEY:
        return "openai"
    return "mock"
