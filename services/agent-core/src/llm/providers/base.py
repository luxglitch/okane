"""
Base provider interface.

Every provider must return:
  text             — the raw string response
  prompt_tokens    — input token count (0 if unavailable)
  completion_tokens — output token count (0 if unavailable)
  cost_usd         — estimated cost in USD (0.0 for local models)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str


class BaseProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1024) -> LLMResponse:
        """Synchronous completion — called in a thread executor if needed."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider+model string for logging."""
        ...
