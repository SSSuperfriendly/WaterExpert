"""LLM client for the knowledge-graph pipeline.

Ported from the ``qcd`` project (``core/llm_client.py``) but configured via
environment variables instead of a checked-in ``.env`` file. The original
``call_llm`` only accepted a single ``prompt`` argument, which the QA page
called with ``system_prompt`` / ``temperature`` kwargs (a latent bug). This
version accepts both optional kwargs so the build and QA paths share one
client.

Required env (a real key must be injected by the operator, never committed):

* ``WATEREXPERT_KG_LLM_API_KEY`` (falls back to ``DASHSCOPE_API_KEY``)
* ``WATEREXPERT_KG_LLM_BASE_URL`` (default: DashScope compatible-mode v1)
* ``WATEREXPERT_KG_LLM_MODEL`` (default: ``qwen-plus``)
"""

from __future__ import annotations

import os

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

_EXTRACTION_SYSTEM_PROMPT = "你是一个知识图谱信息抽取助手，请严格按照用户要求输出 JSON。"


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def get_llm_config() -> dict[str, str]:
    return {
        "api_key": _env("WATEREXPERT_KG_LLM_API_KEY") or _env("DASHSCOPE_API_KEY"),
        "base_url": _env("WATEREXPERT_KG_LLM_BASE_URL")
        or _env("BAILIAN_BASE_URL")
        or DEFAULT_BASE_URL,
        "model": _env("WATEREXPERT_KG_LLM_MODEL")
        or _env("BAILIAN_MODEL")
        or DEFAULT_MODEL,
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
        raise ValueError("请先配置 WATEREXPERT_KG_LLM_API_KEY 环境变量（或 DASHSCOPE_API_KEY）。")

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
