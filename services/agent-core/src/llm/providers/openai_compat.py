"""
OpenAI-compatible provider — used for both DeepSeek and llama.cpp server.

Both expose the same /v1/chat/completions endpoint format, so one implementation
handles both. The difference is just the base_url and api_key.

DeepSeek:
  base_url = https://api.deepseek.com/v1
  api_key  = DEEPSEEK_API_KEY

llama.cpp server:
  base_url = http://llamacpp:8080/v1   (or wherever it's running)
  api_key  = "none"                    (any non-empty string works)
"""
import structlog
from openai import OpenAI

from .base import BaseProvider, LLMResponse

log = structlog.get_logger()

# DeepSeek pricing per 1M tokens (deepseek-chat / deepseek-coder as of 2025)
DEEPSEEK_INPUT_COST_PER_M = 0.14
DEEPSEEK_OUTPUT_COST_PER_M = 0.28

# llama.cpp is local — no cost
LOCAL_COST = 0.0


class OpenAICompatProvider(BaseProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider_label: str = "openai_compat",
        input_cost_per_m: float = 0.0,
        output_cost_per_m: float = 0.0,
    ):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._label = provider_label
        self._input_cost = input_cost_per_m
        self._output_cost = output_cost_per_m

    @property
    def name(self) -> str:
        return f"{self._label}/{self._model}"

    def complete(self, prompt: str, max_tokens: int = 1024) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        pt = resp.usage.prompt_tokens if resp.usage else 0
        ct = resp.usage.completion_tokens if resp.usage else 0
        cost = (pt * self._input_cost + ct * self._output_cost) / 1_000_000
        return LLMResponse(text=text, prompt_tokens=pt, completion_tokens=ct, cost_usd=cost, model=self._model)


def make_deepseek_provider(api_key: str, model: str = "deepseek-chat") -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key=api_key,
        model=model,
        provider_label="deepseek",
        input_cost_per_m=DEEPSEEK_INPUT_COST_PER_M,
        output_cost_per_m=DEEPSEEK_OUTPUT_COST_PER_M,
    )


def _probe_llamacpp_model(base_url: str, fallback: str) -> str:
    """
    Hit GET /v1/models once at startup and return the first model's ID.
    llama.cpp always lists exactly one entry — whatever is currently loaded.
    Falls back to `fallback` if the server isn't reachable.
    """
    import urllib.request
    import urllib.error
    # Strip trailing /v1 if present so we can hit /v1/models cleanly
    root = base_url.rstrip("/")
    if not root.endswith("/v1"):
        root = root + "/v1"
    url = root + "/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            import json as _json
            data = _json.loads(resp.read())
            models = data.get("data", [])
            if models:
                detected = models[0].get("id", fallback)
                log.info("llamacpp_model_detected", model=detected, url=url)
                return detected
    except Exception as exc:
        log.warning("llamacpp_model_probe_failed", url=url, error=str(exc), fallback=fallback)
    return fallback


def make_llamacpp_provider(base_url: str, model: str = "local") -> OpenAICompatProvider:
    # Auto-detect the loaded model from the server; use configured name as fallback
    detected_model = _probe_llamacpp_model(base_url, fallback=model)
    return OpenAICompatProvider(
        base_url=base_url,
        api_key="none",  # llama.cpp server ignores the key
        model=detected_model,
        provider_label="llamacpp",
        input_cost_per_m=LOCAL_COST,
        output_cost_per_m=LOCAL_COST,
    )
