"""
Build the configured LLM provider from settings.

LLM_PROVIDER selects the backend:
  anthropic  — Anthropic Claude (default)
  deepseek   — DeepSeek API (OpenAI-compatible)
  llamacpp   — llama.cpp server (local, OpenAI-compatible)
"""
import structlog

from .base import BaseProvider

log = structlog.get_logger()


def build_provider(settings) -> BaseProvider:
    provider = (settings.llm_provider or "anthropic").lower()

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        from .anthropic_provider import AnthropicProvider
        p = AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    elif provider == "deepseek":
        if not settings.deepseek_api_key:
            raise ValueError("LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY")
        from .openai_compat import make_deepseek_provider
        p = make_deepseek_provider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
        )

    elif provider == "llamacpp":
        from .openai_compat import make_llamacpp_provider
        p = make_llamacpp_provider(
            base_url=settings.llamacpp_base_url,
            model=settings.llamacpp_model,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Choose: anthropic, deepseek, llamacpp"
        )

    log.info("llm_provider_loaded", provider=p.name)
    return p
