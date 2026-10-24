"""Language-model clients behind one small interface.

The agent loop only needs: "here is the conversation and the tools, give me the
next assistant turn (text and/or tool calls)". `OpenAIChatClient` implements that
with the Chat Completions API; `MockLLM` (mock_llm.py) implements it with rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import config


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str | None = None  # set if the model produced invalid JSON


@dataclass
class AssistantTurn:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def as_message(self) -> dict:
        """The turn in Chat Completions message format, for the running conversation."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.raw_arguments or json.dumps(c.arguments)},
                }
                for c in self.tool_calls
            ]
        return message


class LLMClient(Protocol):
    mode: str   # "openai" or "mock"
    model: str

    async def complete(self, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> AssistantTurn: ...


class LLMError(RuntimeError):
    """The model provider rejected or failed the request (auth, quota, bad request...)."""


class OpenAIChatClient:
    mode = "openai"

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        if not config.LLM_API_KEY:
            raise LLMError("LLM_MODE is 'openai' but no LLM_API_KEY is set (see backend/.env.example).")
        self.model = config.LLM_MODEL
        self._client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=2,
        )

    async def complete(self, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> AssistantTurn:
        import openai

        params: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto" if allow_tools else "none"
        if config.LLM_REASONING_EFFORT:
            params["reasoning_effort"] = config.LLM_REASONING_EFFORT
        # No temperature: reasoning-capable models reject sampling parameters.
        try:
            response = await self._client.chat.completions.create(**params)
        except openai.AuthenticationError as exc:
            raise LLMError("The model provider rejected the API key (check LLM_API_KEY).") from exc
        except openai.RateLimitError as exc:
            raise LLMError(f"Rate limit or quota exceeded at the model provider: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(f"Cannot reach the model provider: {exc}") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"The model provider returned an error ({exc.status_code}): {exc.message}") from exc

        message = response.choices[0].message
        calls = []
        for tc in message.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args, error = json.loads(raw), None
                if not isinstance(args, dict):
                    args, error = {}, "arguments must be a JSON object"
            except json.JSONDecodeError as exc:
                args, error = {}, f"invalid JSON arguments: {exc}"
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args, raw_arguments=raw, parse_error=error))
        return AssistantTurn(content=message.content, tool_calls=calls)


def get_llm() -> LLMClient:
    if config.assistant_mode() == "openai":
        return OpenAIChatClient()
    from .mock_llm import MockLLM

    return MockLLM()
