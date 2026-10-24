"""POST /chat: ask the assistant a question."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..agent import answer_question
from ..llm import LLMError
from ..mcp_client import MCPUnavailable
from ..schemas import ChatRequest, ChatResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


@router.post("/chat", response_model=ChatResponse, summary="Ask the contract assistant")
async def chat(request: ChatRequest) -> ChatResponse:
    """Runs the agent loop: the model calls MCP tools as needed, then answers with checked citations."""
    try:
        result = await answer_question(request.message, [m.model_dump() for m in request.history])
    except MCPUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"{exc}. Start it with `python -m mcp_server`.") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(**result.to_dict())
