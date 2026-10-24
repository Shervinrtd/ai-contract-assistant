"""Generate the sample contract PDFs and their metadata file.

Dates are computed relative to the day you run this script, so "expires in
the next 30 days" keeps meaning something whenever the demo is run.

Usage (from the backend folder):
    python -m scripts.generate_contracts
    python -m scripts.generate_contracts --today 2026-10-24   # reproducible run
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app import config
from sample_contracts.builder import COMPANY_NAME, build_all, format_date
from sample_contracts.pdf_writer import write_contract_pdf


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--today", type=date.fromisoformat, help="pretend today is this date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    today: date = args.today or date.today()

    config.CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for doc in build_all(today):
        pages = write_contract_pdf(doc, config.CONTRACTS_DIR / doc.file_name)
        status = "Expired" if doc.expiration_date < today else "Active"
        records.append(
            {
                "id": doc.contract_id,
                "title": doc.title,
                "counterparty": doc.counterparty.name,
                "contract_type": doc.contract_type,
                "effective_date": doc.effective_date.isoformat(),
                "expiration_date": doc.expiration_date.isoformat(),
                "status": status,
                "file": doc.file_name,
            }
        )
        print(
            f"{doc.contract_id}  {doc.title:<45} {pages} pages  "
            f"expires {format_date(doc.expiration_date):<18} {status}"
        )

    metadata = {"generated_on": today.isoformat(), "company": COMPANY_NAME, "contracts": records}
    config.METADATA_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nWrote {len(records)} PDFs and {config.METADATA_FILE.relative_to(config.BACKEND_DIR)}")


if __name__ == "__main__":
    main()
