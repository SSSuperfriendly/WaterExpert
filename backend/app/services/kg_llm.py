"""LLM client for the knowledge-graph pipeline.

Ported from the ``qcd`` project (``core/llm_client.py``) but configured via
environment variables instead of a checked-in ``.env`` file. The original
``call_llm`` only accepted a single ``prompt`` argument, which the QA page
called with ``system_prompt`` / ``temperature`` kwargs (a latent bug). This
version accepts both optional kwargs so the build and QA paths share one
client.

Required env (a real key must be injected by the operator, never committed):

* ``WATEREXPERT_KG_LLM_API_KEY`` (falls back to ``DEEPSEEK_API_KEY``, then
  ``DASHSCOPE_API_KEY``)
* ``WATEREXPERT_KG_LLM_BASE_URL`` and ``WATEREXPERT_KG_LLM_MODEL`` — each
  falling back to ``BAILIAN_BASE_URL`` / ``BAILIAN_MODEL``, then to the
  selected provider's defaults.

Two providers are supported. DeepSeek uses the same key and the same model as
the agent side (``agent/src/water_ai/llm/backends/api_backend.py``), so the two
halves of the product answer with one model.
"""

from __future__ import annotations

import os

#: Per-provider endpoint and default model. DeepSeek uses the same key and the
#: same model as the agent half of the product, so both answer with one model.
PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
}

DEFAULT_PROVIDER = "dashscope"
DEFAULT_BASE_URL = PROVIDERS[DEFAULT_PROVIDER]["base_url"]
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER]["model"]

_EXTRACTION_SYSTEM_PROMPT = "你是一个知识图谱信息抽取助手，请严格按照用户要求输出 JSON。"


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def resolve_provider() -> tuple[str, str]:
    """Pick a provider and the API key to use with it.

    The DeepSeek branch is inserted *below* every existing variable, not
    beside them: a deployment that already sets ``WATEREXPERT_KG_LLM_API_KEY``
    or ``DASHSCOPE_API_KEY`` keeps the exact behaviour it has today. DeepSeek is
    only chosen when those are absent and ``DEEPSEEK_API_KEY`` is present.

    ``WATEREXPERT_KG_LLM_PROVIDER`` overrides the inference outright — that is
    the escape hatch for a deployment whose key lives under a name this
    function does not know about.
    """
    explicit = _env("WATEREXPERT_KG_LLM_PROVIDER").lower()
    generic_key = _env("WATEREXPERT_KG_LLM_API_KEY")
    deepseek_key = _env("DEEPSEEK_API_KEY")
    dashscope_key = _env("DASHSCOPE_API_KEY")

    if explicit in PROVIDERS:
        provider = explicit
    elif generic_key or dashscope_key:
        provider = DEFAULT_PROVIDER
    elif deepseek_key:
        provider = "deepseek"
    else:
        provider = DEFAULT_PROVIDER

    # A generic key is assumed to belong to the provider's own convention, so
    # the named variable for the selected provider wins.
    if provider == "deepseek":
        api_key = deepseek_key or generic_key or dashscope_key
    else:
        api_key = generic_key or dashscope_key or deepseek_key

    return provider, api_key


def get_llm_config() -> dict[str, str]:
    """Resolve the LLM endpoint.

    ``base_url`` and ``model`` are resolved *from the selected provider*, as a
    pair — never independently. Resolving them separately is how ``qwen-plus``
    ends up being sent to DeepSeek and rejected with a 400.
    """
    provider, api_key = resolve_provider()
    defaults = PROVIDERS[provider]

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": _env("WATEREXPERT_KG_LLM_BASE_URL")
        or _env("BAILIAN_BASE_URL")
        or defaults["base_url"],
        "model": _env("WATEREXPERT_KG_LLM_MODEL")
        or _env("BAILIAN_MODEL")
        or defaults["model"],
    }


def is_llm_configured() -> bool:
    return bool(get_llm_config()["api_key"])


def call_llm(
    prompt: str,
    *,
    system_prompt: str | None = None,
    temperature: float = 0.1,
) -> str:
    """Call the configured LLM and return the assistant's text response.

    Raises ``ValueError`` when no API key is configured and ``RuntimeError``
    when the ``openai`` dependency is missing.
    """
    config = get_llm_config()

    if not config["api_key"]:
        raise ValueError(
            "请先配置 WATEREXPERT_KG_LLM_API_KEY、DEEPSEEK_API_KEY 或 "
            "DASHSCOPE_API_KEY 环境变量。"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("未安装 openai 依赖，请执行 pip install openai。") from exc

    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    response = client.chat.completions.create(
        model=config["model"],
        messages=[
            {
                "role": "system",
                "content": system_prompt or _EXTRACTION_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )

    return response.choices[0].message.content or ""
