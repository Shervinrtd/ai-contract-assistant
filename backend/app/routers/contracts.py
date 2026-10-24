"""Contract list endpoints, plus the original PDFs for citation links."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import config, db
from ..schemas import Contract

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _get_or_404(contract_id: str) -> db.ContractRecord:
    record = db.get_contract(contract_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id!r} not found")
    return record


@router.get("", response_model=list[Contract], summary="List all contracts")
def list_contracts() -> list[Contract]:
    """All contracts, soonest expiration first."""
    return [Contract.from_record(r) for r in db.list_contracts()]


@router.get("/{contract_id}", response_model=Contract, summary="Get one contract")
def get_contract(contract_id: str) -> Contract:
    return Contract.from_record(_get_or_404(contract_id))


@router.get(
    "/{contract_id}/pdf",
    response_class=FileResponse,
    summary="Download or view the original contract PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_contract_pdf(contract_id: str) -> FileResponse:
    record = _get_or_404(contract_id)
    # The file name comes from our own database, never from the request path.
    path = config.CONTRACTS_DIR / record.file
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF for {contract_id!r} is missing; re-run setup")
    # "inline" lets the browser display the PDF, so links like .../pdf#page=3 open the right page.
    return FileResponse(path, media_type="application/pdf", filename=record.file, content_disposition_type="inline")
