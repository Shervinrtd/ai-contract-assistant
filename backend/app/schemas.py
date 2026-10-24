"""API response models."""

from __future__ import annotations

from datetime import date

from typing import Literal

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


# ----------------------------------------------------------------- chat


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, examples=["Which contracts expire in the next 30 days?"])
    history: list[ChatMessage] = Field(default_factory=list, description="Earlier turns, oldest first (optional)")


class CitationOut(BaseModel):
    n: int = Field(description="Number used in the answer text, e.g. [1]")
    source_id: str = Field(description="Clause id (C-003:8) or contract id (C-001)")
    kind: Literal["clause", "contract"]
    contract_id: str
    contract_title: str
    label: str = Field(examples=["Master Supply Agreement (C-003), clause 8, pp. 2-3"])
    pdf_url: str = Field(description="Opens the PDF at the cited page", examples=["/contracts/C-003/pdf#page=2"])
    clause_number: str | None = None
    heading: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    quote: str | None = Field(None, description="Start of the cited clause")


class ToolCallOut(BaseModel):
    name: str
    arguments: dict
    ok: bool
    summary: str
    duration_ms: int


class ChatResponse(BaseModel):
    answer: str = Field(description="Markdown text; [n] markers refer to `citations`")
    citations: list[CitationOut]
    tool_calls: list[ToolCallOut] = Field(description="The MCP tools the assistant called, in order")
    grounded: bool = Field(description="False when the answer cites no source")
    mode: Literal["openai", "mock"]
    model: str
    rounds: int
    warnings: list[str]
