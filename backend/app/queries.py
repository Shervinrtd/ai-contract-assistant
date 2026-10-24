"""Contract look-ups behind the MCP tools.

Plain functions over the SQLite store, so they can be tested without MCP and
the date arithmetic lives in Python rather than in the LLM.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from . import db
from .db import ContractRecord

# Words that say nothing about *which* contract is meant ("contracts with Helix").
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "with", "to", "in", "on", "by", "our",
    "all", "any", "show", "list", "me", "contract", "contracts", "agreement", "agreements",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


def search_contracts(
    query: str | None = None, status: str | None = None, today: date | None = None
) -> list[ContractRecord]:
    """Contracts whose id, title, counterparty or type contain every word of the query.

    An empty query matches everything. Status matching ignores case.
    """
    terms = _tokens(query or "")
    results = []
    for record in db.list_contracts(today=today):
        if status and record.status.lower() != status.lower():
            continue
        haystack = " ".join([record.id, record.title, record.counterparty, record.contract_type]).lower()
        if all(term in haystack for term in terms):
            results.append(record)
    return results


def upcoming_expirations(days: int, today: date | None = None) -> tuple[date, date, list[ContractRecord]]:
    """Active contracts expiring between today and today + days (inclusive), soonest first."""
    if days < 0:
        raise ValueError("days must be zero or positive")
    today = today or date.today()
    window_end = today + timedelta(days=days)
    matches = [
        r for r in db.list_contracts(today=today)
        if r.status == "Active" and today <= r.expiration_date <= window_end
    ]
    return today, window_end, matches
