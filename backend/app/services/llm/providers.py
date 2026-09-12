from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

import httpx

from app.config import Settings
from app.services.llm.base import LLMError, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Deterministic offline verifier. Never selectable in production."""

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-rag-v1"

    def _answer(self, user_prompt: str) -> str:
        marker = "RETRIEVED CONTEXT:\n"
        context = user_prompt.split(marker, 1)[1] if marker in user_prompt else ""
        if not context.strip() or context.strip() == "[NO RETRIEVED EVIDENCE]":
            return "I don't have sufficient repository evidence to answer that question."
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        evidence = " ".join(lines[:3])
        return f"Based on the retrieved repository evidence: {evidence}"

    def generate(self, system_prompt: str, user_prompt: str, history=None) -> LLMResponse:
        return LLMResponse(self._answer(user_prompt))

    def stream(self, system_prompt: str, user_prompt: str, history=None) -> Iterator[str]:
        # Deliberately deterministic and dependency-free. This is not a fake
        # production provider; it exists solely for offline integration tests.
        yield self._answer(user_prompt)


class OpenAILLMProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self._model_name = model_name
        self.base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @staticmethod
    def _messages(system_prompt: str, user_prompt: str, history: list[dict[str, str]] | None):
        return [
            {"role": "system", "content": system_prompt},
            *(history or []),
            {"role": "user", "content": user_prompt},
        ]

    def _payload(self, system_prompt, user_prompt, history, stream: bool):
        return {
            "model": self._model_name,
            "messages": self._messages(system_prompt, user_prompt, history),
            "temperature": 0.1,
            "stream": stream,
        }

    def generate(self, system_prompt, user_prompt, history=None) -> LLMResponse:
        try:
            with httpx.Client(timeout=90) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=self._payload(system_prompt, user_prompt, history, False),
                )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError("OpenAI response content is not a string")
                return LLMResponse(text)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(f"OpenAI request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            raise LLMError(f"OpenAI request failed: {type(exc).__name__}") from exc

    def stream(self, system_prompt, user_prompt, history=None) -> Iterable[str]:
        try:
            with httpx.Client(timeout=90) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=self._payload(system_prompt, user_prompt, history, True),
                ) as response:
                    # IMPORTANT: inspect status and consume the body while the
                    # stream context is still open. Never defer this to __exit__.
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="replace")
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data = json.loads(payload)
                            delta = data["choices"][0].get("delta", {}).get("content")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                            raise LLMError("OpenAI returned malformed streaming data") from exc
                        if delta:
                            yield delta
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(f"OpenAI streaming request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            raise LLMError(f"OpenAI streaming request failed: {type(exc).__name__}") from exc


class OllamaLLMProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout: int = 180,
        keep_alive: str = "30m",
        max_tokens: int = 250,
    ):
        self.base_url = base_url.rstrip("/")
        self._model_name = model_name
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    @staticmethod
    def _messages(system_prompt, user_prompt, history):
        return [
            {"role": "system", "content": system_prompt},
            *(history or []),
            {"role": "user", "content": user_prompt},
        ]

    def _payload(self, system_prompt, user_prompt, history, stream: bool = False) -> dict:
        return {
            "model": self._model_name,
            "messages": self._messages(system_prompt, user_prompt, history),
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": 0.2,
            },
        }

    def generate(self, system_prompt, user_prompt, history=None) -> LLMResponse:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/chat",
                    json=self._payload(system_prompt, user_prompt, history, False),
                )
                response.raise_for_status()
                data = response.json()
                text = data["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError("Ollama response content is not a string")
                return LLMResponse(text)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise LLMError(f"Ollama request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            raise LLMError(f"Ollama request failed: {type(exc).__name__}") from exc

    def stream(self, system_prompt, user_prompt, history=None) -> Iterable[str]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=self._payload(system_prompt, user_prompt, history, True),
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="replace")
                        try:
                            data = json.loads(line)
                            delta = data.get("message", {}).get("content")
                        except (json.JSONDecodeError, TypeError) as exc:
                            raise LLMError("Ollama returned malformed streaming data") from exc
                        if delta:
                            yield delta
                        if data.get("done") is True:
                            break
        except LLMError:
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama streaming request failed: {type(exc).__name__}") from exc
        except Exception as exc:
            raise LLMError(f"Ollama streaming request failed: {type(exc).__name__}") from exc


def build_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "none":
        raise LLMError("No LLM provider configured. Set LLM_PROVIDER to openai, ollama, or mock.")
    if settings.environment == "production" and provider == "mock":
        raise LLMError("MockLLMProvider is forbidden in production.")
    if provider == "mock":
        return MockLLMProvider()
    if provider == "openai":
        if not settings.llm_api_key:
            raise LLMError("LLM_PROVIDER=openai but LLM_API_KEY is not set.")
        return OpenAILLMProvider(settings.llm_api_key, settings.llm_model_name, timeout=settings.llm_timeout_seconds)
    if provider == "ollama":
        return OllamaLLMProvider(
            settings.ollama_url,
            settings.llm_model_name,
            timeout=settings.llm_timeout_seconds,
            keep_alive=settings.ollama_keep_alive,
            max_tokens=settings.llm_max_tokens,
        )
    raise LLMError(f"Unknown LLM provider: {provider!r}")
