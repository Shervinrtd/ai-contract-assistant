"""API response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .db import ContractRecord


class Contract(BaseModel):
    id: str = Field(examples=["C-001"])
    title: str
    counterparty: str
    contract_type: str
    effective_date: date
    expiration_date: date
    status: str = Field(description='"Active" or "Expired" (derived from today\'s date)')
    days_until_expiration: int = Field(description="Negative once the contract has expired")
    pdf_url: str = Field(description="Path of the original PDF; append #page=N to open a given page")

    @classmethod
    def from_record(cls, r: ContractRecord) -> "Contract":
        return cls(
            id=r.id,
            title=r.title,
            counterparty=r.counterparty,
            contract_type=r.contract_type,
            effective_date=r.effective_date,
            expiration_date=r.expiration_date,
            status=r.status,
            days_until_expiration=r.days_until_expiration,
            pdf_url=f"/contracts/{r.id}/pdf",
        )
