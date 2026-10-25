"""Contract look-ups behind the MCP tools: date windows, derived status, search."""

from datetime import date

import pytest

from app import config, db, queries

TODAY = date(2026, 10, 24)
RECORDS = [
    {"id": "C-1", "title": "SaaS Subscription Agreement", "counterparty": "Orbis Cloud GmbH",
     "contract_type": "SaaS subscription", "effective_date": "2025-11-14", "expiration_date": "2026-11-13",
     "status": "Active", "file": "c1.pdf"},
    {"id": "C-2", "title": "Office Space Licence Agreement", "counterparty": "Castello Immobiliare S.r.l.",
     "contract_type": "Office lease", "effective_date": "2025-01-08", "expiration_date": "2027-01-07",
     "status": "Active", "file": "c2.pdf"},
    {"id": "C-3", "title": "Master Supply Agreement", "counterparty": "Helix Components S.p.A.",
     "contract_type": "Supply agreement", "effective_date": "2025-12-24", "expiration_date": "2027-12-23",
     "status": "Active", "file": "c3.pdf"},
    # Recorded as Active, but its date has passed: must come back as Expired.
    {"id": "C-4", "title": "Consulting Services Agreement", "counterparty": "Verdi & Partners",
     "contract_type": "Consulting services", "effective_date": "2025-09-15", "expiration_date": "2026-09-14",
     "status": "Active", "file": "c4.pdf"},
]


@pytest.fixture(autouse=True)
def contracts_db(tmp_path, monkeypatch):
    db_file = tmp_path / "contracts.db"
    monkeypatch.setattr(config, "DB_FILE", db_file)
    db.replace_contracts(RECORDS, db_file)


def ids(records):
    return [r.id for r in records]


def test_expirations_in_the_next_30_days():
    today, window_end, records = queries.upcoming_expirations(30, today=TODAY)
    assert (today, window_end) == (TODAY, date(2026, 11, 23))
    assert ids(records) == ["C-1"]


def test_expiration_window_is_inclusive_and_sorted():
    assert ids(queries.upcoming_expirations(20, today=TODAY)[2]) == ["C-1"]       # expires in exactly 20 days
    assert ids(queries.upcoming_expirations(19, today=TODAY)[2]) == []
    assert ids(queries.upcoming_expirations(90, today=TODAY)[2]) == ["C-1", "C-2"]


def test_expired_contracts_are_never_upcoming():
    assert "C-4" not in ids(queries.upcoming_expirations(3650, today=TODAY)[2])


def test_status_is_derived_from_today():
    statuses = {r.id: r.status for r in db.list_contracts(today=TODAY)}
    assert statuses == {"C-1": "Active", "C-2": "Active", "C-3": "Active", "C-4": "Expired"}
    later = {r.id: r.status for r in db.list_contracts(today=date(2026, 11, 20))}
    assert later["C-1"] == "Expired"


def test_negative_window_is_rejected():
    with pytest.raises(ValueError):
        queries.upcoming_expirations(-1, today=TODAY)


@pytest.mark.parametrize(
    "query, status, expected",
    [
        ("Helix", None, ["C-3"]),
        ("contracts with Helix", None, ["C-3"]),        # filler words are ignored
        ("supply agreement", None, ["C-3"]),
        ("office lease", None, ["C-2"]),                 # matches the contract type
        (None, "Expired", ["C-4"]),
        (None, "active", ["C-1", "C-2", "C-3"]),         # status is case-insensitive
        ("Acme", None, []),
    ],
)
def test_search_contracts(query, status, expected):
    assert ids(queries.search_contracts(query, status, today=TODAY)) == expected
