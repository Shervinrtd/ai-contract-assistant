"""Mock mode: a rule-based stand-in for the LLM, for running the app without an API key.

It implements the same interface as the real client, so everything around it is
real: the agent loop, the MCP tool calls, retrieval, citation checking and the UI.
Only the "brain" is replaced: keyword rules decide which tools to call, and the
answer is assembled from the tool results (quoting clauses rather than reasoning
about them). Answers are clearly labelled as coming from mock mode.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .agent import snippet
from .llm import AssistantTurn, ToolCall

MOCK_NOTE = "_Mock mode: this answer was assembled by keyword rules from the tool results, not by a language model._"

_EXPIRY = re.compile(r"\b(expir\w*|ending|end soon|ends? (with)?in|run(s)? out|due for renewal|coming up for renewal)\b")
_AUTO_RENEW = re.compile(r"\b(renew\w*\s+automatic\w*|automatic\w*\s+renew\w*|auto-?renew\w*)\b")
_TOPIC = re.compile(
    r"\b(terminat\w*|renew\w*|notice|fees?|pric\w*|pay\w*|invoic\w*|liabil\w*|confidential\w*|deposit|warrant\w*|"
    r"deliver\w*|data|insurance|governing|jurisdiction|assign\w*|duration|term|intellectual|solicit\w*|"
    r"force majeure|penalt\w*|cap|obligation\w*|clauses?|conditions?|service levels?|support|uptime|cancel\w*)\b"
)
_STATUS = re.compile(r"\b(expired|active)\b")
_LISTING = re.compile(r"\b(list|show|which contracts|what contracts|all contracts|contracts with|do we have|counterpart\w*)\b")
_GENERIC = {
    "a", "an", "the", "and", "or", "of", "for", "with", "to", "in", "on", "by", "our", "we", "us", "is", "are",
    "what", "which", "who", "how", "does", "do", "any", "all", "me", "show", "list", "tell", "about",
    "agreement", "agreements", "contract", "contracts", "services", "s", "p", "l", "r", "gmbh", "ltd", "spa",
}


def _days(question: str) -> int:
    m = re.search(r"(\d+)\s*(day|week|month|year)s?", question)
    if m:
        return int(m.group(1)) * {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
    for word, days in (("quarter", 90), ("month", 30), ("week", 7), ("year", 365)):
        if word in question:
            return days
    return 30


def _topic(question: str) -> tuple[str, str] | None:
    """(word, stem) for the topic the question is about, e.g. ("termination", "termi"), for a keyword check."""
    q = question.lower()
    if _AUTO_RENEW.search(q):
        return "automatic renewal", "renew"
    m = _TOPIC.search(_EXPIRY.sub(" ", q))
    if not m:
        return None
    word = m.group(1)
    return word, (word[:5] if len(word) > 5 else word)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _GENERIC and len(w) > 2}


def _match_contract(question: str, contracts: list[dict]) -> dict | None:
    """The one contract whose title, counterparty or type shares the most words with the question."""
    asked = _words(question)
    scored = sorted(
        ((len(asked & _words(f"{c['title']} {c['counterparty']} {c['contract_type']}")), c) for c in contracts),
        key=lambda pair: pair[0], reverse=True,
    )
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


class MockLLM:
    mode = "mock"
    model = "rule-based mock"

    def __init__(self) -> None:
        self._counter = 0

    # The conversation since the latest user message: (tool name, arguments, payload) per call.
    @staticmethod
    def _results(messages: list[dict]) -> tuple[str, list[tuple[str, dict, Any]]]:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"]
        calls: dict[str, tuple[str, dict]] = {}
        results = []
        for m in messages[last_user + 1:]:
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    calls[tc["id"]] = (tc["function"]["name"], json.loads(tc["function"]["arguments"]))
            elif m["role"] == "tool":
                name, args = calls[m["tool_call_id"]]
                results.append((name, args, json.loads(m["content"])))
        return question, results

    def _call(self, name: str, args: dict) -> ToolCall:
        self._counter += 1
        return ToolCall(id=f"mock_call_{self._counter}", name=name, arguments=args, raw_arguments=json.dumps(args))

    def _plan(self, question: str, results: list[tuple[str, dict, Any]]) -> list[ToolCall]:
        q = question.lower()
        done = {name for name, _, _ in results}
        # "expired contracts" is a status filter; "expiring in the next 30 days" is a time window.
        status_only = bool(re.search(r"\bexpired\b", q)) and not re.search(
            r"\b(next|within|coming|upcoming|soon|days?|weeks?|months?|quarter|year)\b", q)
        wants_expiry = bool(_EXPIRY.search(q)) and not status_only
        wants_renewal = bool(_AUTO_RENEW.search(q))
        # Expiry phrases such as "due for renewal" are not a request to read clauses.
        wants_clauses = wants_renewal or bool(_TOPIC.search(_EXPIRY.sub(" ", q)))
        topic = "automatic renewal of the term" if wants_renewal else question

        # 1. Questions about expirations start with the expiration tool.
        if wants_expiry and "get_upcoming_expirations" not in done:
            return [self._call("get_upcoming_expirations", {"days": _days(q)})]
        if wants_expiry:
            if wants_clauses and "search_contract_clauses" not in done:
                expiring = next(p for n, _, p in results if n == "get_upcoming_expirations")
                return [self._call("search_contract_clauses", {"query": topic, "contract_id": c["id"], "top_k": 2})
                        for c in expiring.get("contracts", [])]
            return []

        # 2. Otherwise look at the contract list first (to resolve names like "the Helix contract").
        if "search_contracts" not in done:
            status = _STATUS.search(q)
            args = {"status": status.group(1).capitalize()} if status and not wants_clauses else {}
            return [self._call("search_contracts", args)]
        if "search_contract_clauses" in done:
            return []
        if not wants_clauses and (_LISTING.search(q) or _STATUS.search(q)):
            return []  # a question about which contracts exist: the contract list answers it

        contracts = next(p for n, _, p in results if n == "search_contracts").get("contracts", [])
        match = _match_contract(question, contracts)
        if match:
            return [self._call("search_contract_clauses", {"query": topic, "contract_id": match["id"], "top_k": 3})]
        if re.search(r"\b(which|any|all|every)\b", q) or "contracts" in q:
            return [self._call("search_contract_clauses", {"query": topic, "group_by_contract": True})]
        return [self._call("search_contract_clauses", {"query": topic, "top_k": 3})]

    def _compose(self, question: str, results: list[tuple[str, dict, Any]]) -> str:
        parts: list[str] = []
        clause_results = [p for n, _, p in results if n == "search_contract_clauses" and "results" in p]
        expiry = next((p for n, _, p in results if n == "get_upcoming_expirations" and "contracts" in p), None)
        listing = next((p for n, _, p in results if n == "search_contracts" and "contracts" in p), None)

        if expiry is not None:
            if expiry["contracts"]:
                parts.append(f"Active contracts expiring between {expiry['today']} and {expiry['window_end']}:")
                parts += [f"- {c['title']} with {c['counterparty']} expires on {c['expiration_date']} "
                          f"({c['days_until_expiration']} days) [{c['id']}]" for c in expiry["contracts"]]
            else:
                parts.append(f"No active contracts expire between {expiry['today']} and {expiry['window_end']}.")

        if clause_results:
            if expiry is not None and expiry["contracts"]:
                parts.append("\nRelevant clauses:")
            topic = _topic(question)
            for payload in clause_results:
                hits = payload["results"]
                if payload.get("weak_matches_only") or not hits:
                    scope = f" in {payload['contract_id']}" if payload.get("contract_id") else ""
                    parts.append(f"The available contracts do not provide enough evidence to answer this{scope}.")
                    continue
                # Best clause per contract; within one contract, keep only near-best matches.
                best: dict[str, list[dict]] = {}
                for h in hits:
                    best.setdefault(h["contract_id"], []).append(h)
                for contract_hits in best.values():
                    top = contract_hits[0]["score"]
                    keep = [h for h in contract_hits if h["score"] >= top - 0.1][:1 if payload.get("group_by_contract") else 2]
                    if topic and not any(topic[1] in h["text"].lower() for h in keep):
                        parts.append(f"- {keep[0]['contract_title']}: no clause mentions {topic[0]}, so the "
                                     "contract text does not provide enough evidence on this point.")
                        continue
                    for h in keep:
                        clause = f"clause {h['clause_number']} ({h['heading']})" if h["clause_number"] else h["heading"]
                        parts.append(f"- {h['contract_title']}, {clause}: \"{snippet(h['text'], 260)}\" [{h['chunk_id']}]")
        elif expiry is None and listing is not None:
            contracts = listing["contracts"]
            match = _match_contract(question, contracts)
            shown = [match] if match else contracts
            if shown:
                parts.append("Matching contracts:")
                parts += [f"- {c['title']} with {c['counterparty']} ({c['status']}, expires {c['expiration_date']}) "
                          f"[{c['id']}]" for c in shown]
            else:
                parts.append("No contracts match this question.")

        if not parts:
            parts.append("The available contracts do not provide enough evidence to answer this question.")
        return "\n".join(parts) + "\n\n" + MOCK_NOTE

    async def complete(self, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> AssistantTurn:
        question, results = self._results(messages)
        calls = self._plan(question, results) if allow_tools else []
        if calls:
            return AssistantTurn(content=None, tool_calls=calls)
        return AssistantTurn(content=self._compose(question, results))
