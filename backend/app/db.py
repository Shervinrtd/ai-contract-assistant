"""SQLite store for contract metadata (the data behind the contract list).

The table is filled at setup time from data/contracts/metadata.json. Status is
re-derived from today's date on every read, so a contract that passes its
expiration date shows as "Expired" without re-running setup.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    counterparty    TEXT NOT NULL,
    contract_type   TEXT NOT NULL,
    effective_date  TEXT NOT NULL,   -- ISO date
    expiration_date TEXT NOT NULL,   -- ISO date
    status          TEXT NOT NULL,   -- lifecycle status recorded in the metadata
    file            TEXT NOT NULL    -- PDF file name inside CONTRACTS_DIR
);
"""


class DatabaseNotReady(RuntimeError):
    """Raised when setup has not been run yet."""


@dataclass(frozen=True)
class ContractRecord:
    id: str
    title: str
    counterparty: str
    contract_type: str
    effective_date: date
    expiration_date: date
    status: str
    days_until_expiration: int
    file: str


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def replace_contracts(records: list[dict], db_path: Path | None = None) -> int:
    """Recreate the contracts table from metadata records. Returns the row count."""
    path = db_path or config.DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # The database is a derived artifact: rebuild it from scratch on every setup run
    # (this also clears any journal left behind by an interrupted run).
    for leftover in (path, path.with_name(path.name + "-journal"), path.with_name(path.name + "-wal")):
        leftover.unlink(missing_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO contracts (id, title, counterparty, contract_type, effective_date,"
            " expiration_date, status, file) VALUES (:id, :title, :counterparty, :contract_type,"
            " :effective_date, :expiration_date, :status, :file)",
            records,
        )
    conn.close()
    return len(records)


def derive_status(stored_status: str, expiration: date, today: date) -> str:
    return "Expired" if expiration < today else ("Active" if stored_status == "Expired" else stored_status)


def _to_record(row: sqlite3.Row, today: date) -> ContractRecord:
    expiration = date.fromisoformat(row["expiration_date"])
    return ContractRecord(
        id=row["id"],
        title=row["title"],
        counterparty=row["counterparty"],
        contract_type=row["contract_type"],
        effective_date=date.fromisoformat(row["effective_date"]),
        expiration_date=expiration,
        status=derive_status(row["status"], expiration, today),
        days_until_expiration=(expiration - today).days,
        file=row["file"],
    )


def _query(sql: str, params: tuple = (), db_path: Path | None = None) -> list[sqlite3.Row]:
    path = db_path or config.DB_FILE
    if not path.exists():
        raise DatabaseNotReady(
            "Contract database not found. Run `python -m scripts.generate_contracts` "
            "and `python -m scripts.ingest` in the backend folder first."
        )
    conn = connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def list_contracts(today: date | None = None, db_path: Path | None = None) -> list[ContractRecord]:
    """All contracts, soonest expiration first."""
    today = today or date.today()
    rows = _query("SELECT * FROM contracts ORDER BY expiration_date, id", db_path=db_path)
    return [_to_record(r, today) for r in rows]


def get_contract(contract_id: str, today: date | None = None, db_path: Path | None = None) -> ContractRecord | None:
    today = today or date.today()
    rows = _query("SELECT * FROM contracts WHERE id = ?", (contract_id,), db_path=db_path)
    return _to_record(rows[0], today) if rows else None
