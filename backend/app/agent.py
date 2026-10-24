"""The assistant: an LLM that answers contract questions by calling the MCP tools.

One question = one loop:

1. Connect to the MCP server and list its tools (name, description, JSON schema).
2. Give the model the conversation plus those tools as function definitions.
3. If the model asks for tool calls, execute each one through MCP and append the
   results to the conversation. Repeat (up to AGENT_MAX_ROUNDS).
4. When the model answers in text, check its citations against the tool results:
   markers such as [C-003:8] that match a retrieved clause become numbered
   citations with a PDF page link; anything that was not retrieved is removed.

Nothing about the contracts is put in the prompt: everything the model knows
comes from tool results in this conversation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from mcp import ClientSession
from mcp.types import Tool

from . import config
from .llm import LLMClient, ToolCall, get_llm
from .mcp_client import mcp_session, result_payload

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the contract assistant of {company}; today's date is {today}.

You answer questions about the company's contracts. You know nothing about the contracts except what the tools return, so always use them:
- search_contract_clauses: for anything about what a contract says (termination, renewal, notice periods, fees, liability, obligations...). Answer only from the clause text it returns. For questions about all contracts ("which contracts...?") set group_by_contract to true. To search one contract you know only by name, first get its id with search_contracts.
- search_contracts: which contracts exist, with whom, their type, status and dates.
- get_upcoming_expirations: contracts expiring within a period. Never work out dates yourself.

Citations: after each statement based on a tool result, cite its source in square brackets: the clause id for clause text, e.g. [C-003:8], or the contract id for contract data, e.g. [C-001]. Only cite ids that appear in the tool results.

If the tool results do not contain the answer, say plainly that the available contracts do not provide enough evidence, and do not guess or use outside knowledge. Keep answers short and factual."""


# ----------------------------------------------------------------- results


@dataclass
class Citation:
    n: int
    source_id: str          # "C-003:8" (clause) or "C-001" (contract)
    kind: str               # "clause" or "contract"
    contract_id: str
    contract_title: str
    label: str              # "Master Supply Agreement (C-003), clause 8, pp. 2-3"
    pdf_url: str            # "/contracts/C-003/pdf#page=2"
    clause_number: str | None = None
    heading: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    quote: str | None = None


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str
    duration_ms: int


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation]
    tool_calls: list[ToolTrace]
    mode: str
    model: str
    rounds: int
    warnings: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return bool(self.citations)

    def to_dict(self) -> dict:
        return {**asdict(self), "grounded": self.grounded}


# ---------------------------------------------------------------- helpers


def to_openai_tool(tool: Tool) -> dict:
    """MCP tool definition -> Chat Completions function definition (same JSON schema)."""
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.inputSchema},
    }


def _company_name() -> str:
    try:
        return json.loads(config.METADATA_FILE.read_text(encoding="utf-8")).get("company") or "the company"
    except (OSError, ValueError):
        return "the company"


def system_prompt(today: date | None = None) -> str:
    return SYSTEM_PROMPT.format(company=_company_name(), today=(today or date.today()).isoformat())


def _clean_history(history: list[dict] | None, limit: int = 8) -> list[dict]:
    """Keep only plain user/assistant text turns from the client."""
    turns = [
        {"role": m["role"], "content": m["content"]}
        for m in history or []
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip()
    ]
    return turns[-limit:]


def _summarise(name: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:120]
    if name == "search_contract_clauses":
        hits = payload.get("results", [])
        ids = ", ".join(h["chunk_id"] for h in hits[:6])
        weak = " (weak matches only)" if payload.get("weak_matches_only") else ""
        return f"{len(hits)} clause(s){weak}: {ids}" if hits else "no clauses"
    if "contracts" in payload:
        ids = ", ".join(c["id"] for c in payload["contracts"])
        window = f" expiring by {payload['window_end']}" if "window_end" in payload else ""
        return f"{payload.get('count', 0)} contract(s){window}" + (f": {ids}" if ids else "")
    return json.dumps(payload, default=str)[:120]


def snippet(markdown: str, limit: int = 300) -> str:
    lines = [l for l in markdown.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    text = " ".join(re.sub(r"^\s*-\s+", "", l) for l in lines)
    text = re.sub(r"\s+", " ", text.replace("**", "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


@dataclass
class _Evidence:
    """Everything the tools returned in this conversation, by id."""

    clauses: dict[str, dict] = field(default_factory=dict)
    contracts: dict[str, dict] = field(default_factory=dict)

    def collect(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for c in payload.get("contracts", []):
            self.contracts[c["id"]] = c
        for h in payload.get("results", []):
            self.clauses[h["chunk_id"]] = h
            self.contracts.setdefault(h["contract_id"], {"id": h["contract_id"], "title": h["contract_title"]})


_MARKER = re.compile(r"\[([^\[\]\n]{1,200})\]")
_SOURCE_ID = re.compile(r"^C-\d+(?::[A-Za-z0-9-]+)*$")


def apply_citations(answer: str, evidence: _Evidence) -> tuple[str, list[Citation], list[str]]:
    """Turn [C-003:8]-style markers into numbered citations; drop markers with no matching tool result."""
    numbers: dict[str, int] = {}
    citations: list[Citation] = []
    warnings: list[str] = []

    def build(source_id: str, n: int) -> Citation | None:
        if source_id in evidence.clauses:
            h = evidence.clauses[source_id]
            return Citation(
                n=n, source_id=source_id, kind="clause", contract_id=h["contract_id"],
                contract_title=h["contract_title"], label=h["citation"],
                pdf_url=f"/contracts/{h['contract_id']}/pdf#page={h['page_start']}",
                clause_number=h.get("clause_number"), heading=h.get("heading"),
                page_start=h["page_start"], page_end=h["page_end"], quote=snippet(h["text"]),
            )
        if source_id in evidence.contracts:
            c = evidence.contracts[source_id]
            return Citation(
                n=n, source_id=source_id, kind="contract", contract_id=source_id,
                contract_title=c.get("title", source_id), label=f"{c.get('title', source_id)} ({source_id})",
                pdf_url=f"/contracts/{source_id}/pdf",
            )
        return None

    def replace(match: re.Match) -> str:
        parts = [re.sub(r"^c-", "C-", p.strip()) for p in re.split(r"[,;]", match.group(1))]
        if not parts or not all(_SOURCE_ID.match(p) for p in parts):
            return match.group(0)  # ordinary bracketed text, not a citation
        out = []
        for source_id in parts:
            if source_id not in numbers:
                citation = build(source_id, len(citations) + 1)
                if citation is None:
                    warnings.append(f"Removed citation [{source_id}]: no tool result in this conversation has that id.")
                    continue
                numbers[source_id] = citation.n
                citations.append(citation)
            out.append(f"[{numbers[source_id]}]")
        return "".join(out)

    text = _MARKER.sub(replace, answer)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)  # tidy spaces left by removed markers
    return text.strip(), citations, warnings


async def _execute(session: ClientSession, call: ToolCall, known_tools: set[str]) -> tuple[Any, bool]:
    if call.parse_error:
        return {"error": f"Could not parse the tool arguments: {call.parse_error}"}, False
    if call.name not in known_tools:
        return {"error": f"Unknown tool {call.name!r}. Available: {sorted(known_tools)}"}, False
    result = await session.call_tool(call.name, call.arguments)
    if result.isError:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        return {"error": text}, False
    return result_payload(result), True


# -------------------------------------------------------------------- loop


async def answer_question(question: str, history: list[dict] | None = None, llm: LLMClient | None = None) -> AgentResult:
    llm = llm or get_llm()
    evidence = _Evidence()
    trace: list[ToolTrace] = []
    warnings: list[str] = []

    async with mcp_session() as session:
        tools = (await session.list_tools()).tools
        tool_specs = [to_openai_tool(t) for t in tools]
        known = {t.name for t in tools}

        messages: list[dict] = [{"role": "system", "content": system_prompt()}]
        messages += _clean_history(history)
        messages.append({"role": "user", "content": question})

        answer, rounds = None, 0
        for rounds in range(1, config.AGENT_MAX_ROUNDS + 1):
            turn = await llm.complete(messages, tool_specs)
            if not turn.tool_calls:
                answer = turn.content or ""
                break
            messages.append(turn.as_message())
            for call in turn.tool_calls:
                started = time.perf_counter()
                payload, ok = await _execute(session, call, known)
                elapsed = int((time.perf_counter() - started) * 1000)
                if ok:
                    evidence.collect(payload)
                summary = _summarise(call.name, payload) if ok else payload["error"][:200]
                log.info("tool %s(%s) -> %s", call.name, call.arguments, summary)
                trace.append(ToolTrace(call.name, call.arguments, ok, summary, elapsed))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(payload, default=str)})

        if answer is None:  # still asking for tools after the last round: ask for a final answer
            warnings.append(f"Stopped after {config.AGENT_MAX_ROUNDS} tool rounds.")
            turn = await llm.complete(messages, tool_specs, allow_tools=False)
            answer = turn.content or ""

    if not answer.strip():
        answer = "I could not produce an answer to this question."
        warnings.append("The model returned an empty answer.")

    text, citations, citation_warnings = apply_citations(answer, evidence)
    return AgentResult(
        answer=text,
        citations=citations,
        tool_calls=trace,
        mode=llm.mode,
        model=llm.model,
        rounds=rounds,
        warnings=warnings + citation_warnings,
    )
