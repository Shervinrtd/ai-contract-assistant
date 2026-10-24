"""Ingest the contract PDFs: extract Markdown page by page and split it into clause chunks.

Inputs : data/contracts/*.pdf and data/contracts/metadata.json (from generate_contracts)
Outputs: data/extracted/<id>.md  (what the model will "see", for inspection)
         data/chunks.json        (clause chunks with page ranges)

Later steps extend this script to load the metadata into SQLite and build the
vector index, so setup stays a single command.

Usage (from the backend folder):
    python -m scripts.ingest [--show-chunks]
"""

from __future__ import annotations

import argparse
import json

from app import config
from app.ingestion.chunking import chunk_contract
from app.ingestion.pdf_extract import extract_pages, pages_to_markdown


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show-chunks", action="store_true", help="print every chunk with its page range")
    args = parser.parse_args(argv)

    if not config.METADATA_FILE.exists():
        raise SystemExit("No contracts found. Run `python -m scripts.generate_contracts` first.")
    metadata = json.loads(config.METADATA_FILE.read_text(encoding="utf-8"))

    config.EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks = []
    for record in metadata["contracts"]:
        pdf_path = config.CONTRACTS_DIR / record["file"]
        pages = extract_pages(pdf_path)
        md_path = config.EXTRACTED_DIR / f"{record['id']}.md"
        md_path.write_text(pages_to_markdown(pages, pdf_path.name), encoding="utf-8")

        chunks = chunk_contract(pages, record["id"], record["title"], record["counterparty"])
        all_chunks.extend(chunks)
        print(f"{record['id']}  {record['title']:<45} {len(pages)} pages -> {len(chunks)} chunks")
        if args.show_chunks:
            for c in chunks:
                pages_label = str(c.page_start) if c.page_start == c.page_end else f"{c.page_start}-{c.page_end}"
                print(f"    {c.chunk_id:<34} p.{pages_label:<5} {c.heading}")

    config.CHUNKS_FILE.write_text(json.dumps([c.to_dict() for c in all_chunks], indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_chunks)} chunks to {config.CHUNKS_FILE.relative_to(config.BACKEND_DIR)}")


if __name__ == "__main__":
    main()
