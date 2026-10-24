"""Ask the assistant from the command line (needs the MCP server running).

Usage (from the backend folder):
    python -m scripts.ask "Which contracts expire in the next 30 days?"
    python -m scripts.ask --demo            # the six demo questions from the design doc
    python -m scripts.ask --mock "..."      # force mock mode even if an API key is set
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

DEMO_QUESTIONS = [
    "Which contracts expire in the next 30 days?",
    "Which contracts renew automatically?",
    "What are the termination conditions in the supply agreement?",
    "Show me all contracts with Helix",
    "What are the termination conditions in the NDA?",
    "Of the contracts expiring in the next 90 days, which renew automatically?",
]


def _print(result) -> None:
    print(f"[{result.mode} · {result.model} · {result.rounds} round(s)]")
    for t in result.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in t.arguments.items())
        print(f"  tool: {t.name}({args}) -> {t.summary}{'' if t.ok else '  [ERROR]'}")
    print("\n" + result.answer)
    if result.citations:
        print("\nSources:")
        for c in result.citations:
            print(f"  [{c.n}] {c.label}  ->  {c.pdf_url}")
    else:
        print("\n(no sources cited)")
    for w in result.warnings:
        print(f"  warning: {w}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="*", help="the question to ask")
    parser.add_argument("--demo", action="store_true", help="run the six demo questions")
    parser.add_argument("--mock", action="store_true", help="use mock mode")
    args = parser.parse_args(argv)
    if args.mock:
        os.environ["LLM_MODE"] = "mock"

    from app.agent import answer_question  # imported after LLM_MODE is set
    from app.llm import LLMError
    from app.mcp_client import MCPUnavailable

    questions = DEMO_QUESTIONS if args.demo else [" ".join(args.question)]
    if not questions[0]:
        parser.error("give a question or use --demo")
    for i, question in enumerate(questions, start=1):
        print(f"\n{'=' * 100}\nQ{i}: {question}")
        try:
            _print(await answer_question(question))
        except MCPUnavailable as exc:
            print(exc, "\nStart the MCP server first: python -m mcp_server")
            return 1
        except LLMError as exc:
            print("Model error:", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
