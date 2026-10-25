"""Mock mode picks the same tools a model would, and says so when evidence is missing."""

import asyncio
import json

from app.mock_llm import MOCK_NOTE, MockLLM

CONTRACTS = {"count": 2, "contracts": [
    {"id": "C-003", "title": "Master Supply Agreement", "counterparty": "Helix Components S.p.A.",
     "contract_type": "Supply agreement", "status": "Active", "expiration_date": "2027-12-23"},
    {"id": "C-004", "title": "Mutual Non-Disclosure Agreement", "counterparty": "Brightline Analytics Ltd",
     "contract_type": "NDA", "status": "Active", "expiration_date": "2028-10-23"},
]}


def turn(question, results=()):
    """Run one mock step after the given (tool name, arguments, result) history."""
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": question}]
    for i, (name, args, payload) in enumerate(results):
        call_id = f"call_{i}"
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload)})
    return asyncio.run(MockLLM().complete(messages, []))


def first_call(t):
    return t.tool_calls[0].name, t.tool_calls[0].arguments


def test_expiration_window_goes_to_the_expiration_tool():
    assert first_call(turn("Which contracts expire in the next 3 months?")) == ("get_upcoming_expirations", {"days": 90})


def test_expired_contracts_is_a_status_filter():
    assert first_call(turn("List the expired contracts")) == ("search_contracts", {"status": "Expired"})


def test_named_contract_is_resolved_before_searching_its_clauses():
    question = "What are the termination conditions in the supply agreement?"
    assert first_call(turn(question)) == ("search_contracts", {})
    name, args = first_call(turn(question, [("search_contracts", {}, CONTRACTS)]))
    assert name == "search_contract_clauses" and args["contract_id"] == "C-003"


def test_weak_matches_lead_to_an_insufficient_evidence_answer():
    weak = {"results": [], "weak_matches_only": True, "contract_id": None, "group_by_contract": False}
    answer = turn("What is our parental leave policy?",
                  [("search_contracts", {}, CONTRACTS), ("search_contract_clauses", {"query": "x"}, weak)])
    assert not answer.tool_calls
    assert "do not provide enough evidence" in answer.content and MOCK_NOTE in answer.content
