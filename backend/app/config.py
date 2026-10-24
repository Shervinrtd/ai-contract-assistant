"""Central configuration: file locations used by the backend and the setup scripts."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Everything generated at setup time lives under DATA_DIR (gitignored).
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data")).resolve()

CONTRACTS_DIR = DATA_DIR / "contracts"          # generated PDFs
METADATA_FILE = CONTRACTS_DIR / "metadata.json"  # list metadata written by the generator
EXTRACTED_DIR = DATA_DIR / "extracted"           # Markdown extracted from each PDF (for inspection)
CHUNKS_FILE = DATA_DIR / "chunks.json"           # clause-level chunks with page ranges
