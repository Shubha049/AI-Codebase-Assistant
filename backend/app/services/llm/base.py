from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


class LLMError(RuntimeError):
    """Provider or transport failure that can be safely surfaced as a 502."""


@dataclass(frozen=True)
class LLMResponse:
    text: str


class LLMProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> Iterable[str]:
        """Yield answer deltas. Providers without native streaming get one delta."""
        yield self.generate(system_prompt, user_prompt, history).text
