import anthropic
import structlog

from .base import BaseProvider, LLMResponse

log = structlog.get_logger()

# Cost per 1M tokens (claude-sonnet-4-6)
INPUT_COST_PER_M = 3.0
OUTPUT_COST_PER_M = 15.0


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(self, prompt: str, max_tokens: int = 1024) -> LLMResponse:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        pt = message.usage.input_tokens
        ct = message.usage.output_tokens
        cost = (pt * INPUT_COST_PER_M + ct * OUTPUT_COST_PER_M) / 1_000_000
        return LLMResponse(text=text, prompt_tokens=pt, completion_tokens=ct, cost_usd=cost, model=self._model)
