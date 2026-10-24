"""Contract tools served over MCP (Streamable HTTP).

The tool descriptions below are what the LLM reads when deciding which tool to
call, so they are written like documentation: what the tool does, when to use
it, and what it returns.

Run from the backend folder:
    python -m mcp_server            # serves http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app import queries, retrieval
from app.db import ContractRecord

log = logging.getLogger("mcp_server")

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8001"))

mcp = FastMCP(
    name="contract-tools",
    instructions=(
        "Tools for looking up the company's contracts. Use search_contracts to find contracts "
        "by name, counterparty, type or status; get_upcoming_expirations for questions about "
        "contracts expiring within a period; and search_contract_clauses to read what the contracts "
        "actually say, with citations. All dates are ISO (YYYY-MM-DD)."
    ),
    host=HOST,
    port=PORT,
    stateless_http=True,  # every request is independent; nothing to clean up between calls
)


# ------------------------------------------------------------------ results


class ContractSummary(BaseModel):
    id: str = Field(description="Contract id, e.g. C-001")
    title: str
    counterparty: str
    contract_type: str
    effective_date: date
    expiration_date: date
    status: str = Field(description='"Active" or "Expired"')
    days_until_expiration: int = Field(description="Negative if already expired")

    @classmethod
    def from_record(cls, r: ContractRecord) -> "ContractSummary":
        return cls(
            id=r.id,
            title=r.title,
            counterparty=r.counterparty,
            contract_type=r.contract_type,
            effective_date=r.effective_date,
            expiration_date=r.expiration_date,
            status=r.status,
            days_until_expiration=r.days_until_expiration,
        )


class SearchContractsResult(BaseModel):
    query: str | None
    status: str | None
    count: int
    contracts: list[ContractSummary]


class UpcomingExpirationsResult(BaseModel):
    today: date
    window_end: date = Field(description="Last day of the search window (today + days)")
    days: int
    count: int
    contracts: list[ContractSummary] = Field(description="Active contracts in the window, soonest first")


class ClauseResult(BaseModel):
    chunk_id: str = Field(description="Stable id of the clause chunk, e.g. C-003:8")
    contract_id: str
    contract_title: str
    counterparty: str
    clause_number: str | None = Field(description="None for the preamble or signature block")
    heading: str
    page_start: int
    page_end: int
    citation: str = Field(description="Ready-made citation, e.g. 'Master Supply Agreement (C-003), clause 8, pp. 2-3'")
    score: float = Field(description="Similarity to the query, 0-1; above ~0.4 is a strong match")
    text: str = Field(description="The clause text as extracted from the PDF")


class SearchClausesResult(BaseModel):
    query: str
    contract_id: str | None
    group_by_contract: bool
    contracts_checked: list[str]
    contracts_without_match: list[str] = Field(
        description="Contracts searched where no clause scored above the relevance threshold"
    )
    weak_matches_only: bool = Field(description="True if nothing matched well; results are only the closest passages")
    note: str | None = None
    results: list[ClauseResult]


# -------------------------------------------------------------------- tools


@mcp.tool()
def search_contracts(
    query: Annotated[
        str | None,
        Field(description="Words to match against the contract title, counterparty and type, "
                          "e.g. 'Helix', 'supply agreement' or 'NDA'. Omit to list all contracts."),
    ] = None,
    status: Annotated[
        Literal["Active", "Expired"] | None,
        Field(description="Only return contracts with this status."),
    ] = None,
) -> SearchContractsResult:
    """Find contracts by title, counterparty, contract type and/or status.

    Use this to see which contracts exist with a given company, to find a contract's id
    (needed to search inside a specific contract), or to list all active or expired
    contracts. Returns contract metadata only (dates, status, parties), not clause text.
    Every word in `query` must match; an empty result means no contract matched.
    """
    log.info("tool call: search_contracts(query=%r, status=%r)", query, status)
    records = queries.search_contracts(query, status)
    return SearchContractsResult(
        query=query, status=status, count=len(records),
        contracts=[ContractSummary.from_record(r) for r in records],
    )


@mcp.tool()
def get_upcoming_expirations(
    days: Annotated[
        int,
        Field(ge=0, le=3650, description="Size of the window in days from today, e.g. 30 for "
                                         "'the next 30 days', 90 for 'the next three months'."),
    ],
) -> UpcomingExpirationsResult:
    """List active contracts whose expiration date falls between today and `days` days from today.

    Use this for any question about contracts expiring, ending or coming up for renewal
    within a period ("what expires in the next 30 days?", "anything ending this quarter?").
    The date arithmetic is done here, so do not work out expirations yourself. Results are
    sorted soonest first; already-expired contracts are not included.
    """
    log.info("tool call: get_upcoming_expirations(days=%r)", days)
    today, window_end, records = queries.upcoming_expirations(days)
    return UpcomingExpirationsResult(
        today=today, window_end=window_end, days=days, count=len(records),
        contracts=[ContractSummary.from_record(r) for r in records],
    )


@mcp.tool()
def search_contract_clauses(
    query: Annotated[
        str,
        Field(min_length=2, description="What to look for, in contract language, e.g. 'termination for "
                                        "convenience notice period', 'automatic renewal', 'limitation of "
                                        "liability cap'. Turn casual wording ('get out of the deal early') "
                                        "into the legal term ('early termination')."),
    ],
    contract_id: Annotated[
        str | None,
        Field(description="Restrict the search to one contract, e.g. 'C-003'. If you only know the name "
                          "or counterparty, call search_contracts first to get the id."),
    ] = None,
    group_by_contract: Annotated[
        bool,
        Field(description="Set to true for questions that must be checked in every contract, e.g. 'which "
                          "contracts renew automatically?'. Returns the best clauses from each contract "
                          "instead of the overall top matches. Ignored when contract_id is given."),
    ] = False,
    top_k: Annotated[int, Field(ge=1, le=10, description="Maximum number of clauses (when not grouping).")] = 5,
) -> SearchClausesResult:
    """Search the text of the contracts and return the most relevant clauses, with citations.

    Use this for any question about what the contracts say: termination, renewal, notice
    periods, fees, liability, confidentiality, data protection, obligations and so on.
    Each result has the clause text and a citation (contract, clause number, pages).
    Answer only from the returned text and cite it. If `weak_matches_only` is true,
    nothing matched well: rephrase the query once in contract terms, and if that still
    finds nothing, say the contracts do not provide enough evidence.
    """
    cid = contract_id.strip().upper() if contract_id else None
    log.info("tool call: search_contract_clauses(query=%r, contract_id=%r, group_by_contract=%r, top_k=%r)",
             query, cid, group_by_contract, top_k)
    if cid and cid not in retrieval.contract_ids():
        raise ValueError(f"Unknown contract id {cid!r}. Use search_contracts to find valid ids.")

    outcome = retrieval.search(query, contract_id=cid, top_k=top_k, group_by_contract=group_by_contract)
    note = None
    if outcome.weak_matches_only:
        note = ("No clause matched strongly. These are only the closest passages and may not answer "
                "the question; rephrase in contract terms or report insufficient evidence.")
    return SearchClausesResult(
        query=query,
        contract_id=cid,
        group_by_contract=group_by_contract and not cid,
        contracts_checked=outcome.contracts_checked,
        contracts_without_match=outcome.contracts_without_match,
        weak_matches_only=outcome.weak_matches_only,
        note=note,
        results=[ClauseResult(**h.to_dict()) for h in outcome.hits],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Keep the console readable: hide the SDK's per-request chatter, keep our tool-call lines.
    for noisy in ("mcp.server.streamable_http", "mcp.server.streamable_http_manager", "mcp.server.lowlevel.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        retrieval.warm_up()  # load the embedding model now rather than on the first question
    except Exception as exc:  # keep serving the other tools; the clause tool will report the problem
        log.warning("clause search not ready: %s", exc)
    log.info("MCP server listening on http://%s:%s/mcp", HOST, PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
