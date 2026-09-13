"""Provider resolution for the knowledge-graph LLM client.

The whole point of these is the backward-compatibility guarantee: a deployment
that already sets ``WATEREXPERT_KG_LLM_API_KEY`` or ``DASHSCOPE_API_KEY`` must
resolve to exactly what it resolved to before DeepSeek was added. The DeepSeek
branch is inserted *below* those variables, never beside them.

The other half is the pairing rule. ``base_url`` and ``model`` must come from
the *same* provider — resolving them independently is how ``qwen-plus`` gets
sent to DeepSeek and rejected with a 400.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.services import kg_llm


class ResolveProviderTest(unittest.TestCase):
    def resolve(self, **env: str) -> tuple[str, str]:
        cleaned = {key: value for key, value in env.items() if value is not None}
        with patch.dict("os.environ", cleaned, clear=True):
            return kg_llm.resolve_provider()

    def test_deepseek_key_alone_selects_deepseek(self) -> None:
        self.assertEqual(self.resolve(DEEPSEEK_API_KEY="sk-ds"), ("deepseek", "sk-ds"))

    def test_generic_key_keeps_dashscope(self) -> None:
        # The pre-existing variable wins outright, even alongside a DeepSeek
        # key — that is what makes this change safe to deploy.
        self.assertEqual(
            self.resolve(WATEREXPERT_KG_LLM_API_KEY="sk-generic", DEEPSEEK_API_KEY="sk-ds"),
            ("dashscope", "sk-generic"),
        )

    def test_dashscope_key_keeps_dashscope(self) -> None:
        self.assertEqual(
            self.resolve(DASHSCOPE_API_KEY="sk-dash", DEEPSEEK_API_KEY="sk-ds"),
            ("dashscope", "sk-dash"),
        )

    def test_explicit_provider_overrides_inference(self) -> None:
        self.assertEqual(
            self.resolve(WATEREXPERT_KG_LLM_PROVIDER="deepseek", WATEREXPERT_KG_LLM_API_KEY="sk-x"),
            ("deepseek", "sk-x"),
        )
        self.assertEqual(
            self.resolve(WATEREXPERT_KG_LLM_PROVIDER="dashscope", DEEPSEEK_API_KEY="sk-ds"),
            ("dashscope", "sk-ds"),
        )

    def test_unknown_provider_string_falls_back_to_inference(self) -> None:
        self.assertEqual(
            self.resolve(WATEREXPERT_KG_LLM_PROVIDER="openai", DEEPSEEK_API_KEY="sk-ds"),
            ("deepseek", "sk-ds"),
        )

    def test_nothing_configured(self) -> None:
        self.assertEqual(self.resolve(), ("dashscope", ""))


class GetLlmConfigTest(unittest.TestCase):
    def config(self, **env: str) -> dict[str, str]:
        cleaned = {key: value for key, value in env.items() if value is not None}
        with patch.dict("os.environ", cleaned, clear=True):
            return kg_llm.get_llm_config()

    def test_deepseek_resolves_the_deepseek_pair(self) -> None:
        # The failure this guards against: a bare DeepSeek key with the
        # DashScope base_url/model still set would send qwen-plus to DeepSeek.
        config = self.config(DEEPSEEK_API_KEY="sk-ds")
        self.assertEqual(config["provider"], "deepseek")
        self.assertEqual(config["base_url"], "https://api.deepseek.com/v1")
        self.assertEqual(config["model"], "deepseek-chat")

    def test_defaults_are_dashscope(self) -> None:
        config = self.config(WATEREXPERT_KG_LLM_API_KEY="sk-x")
        self.assertEqual(config["provider"], "dashscope")
        self.assertEqual(config["base_url"], kg_llm.DEFAULT_BASE_URL)
        self.assertEqual(config["model"], "qwen-plus")

    def test_explicit_overrides_win_within_a_provider(self) -> None:
        config = self.config(
            DEEPSEEK_API_KEY="sk-ds",
            WATEREXPERT_KG_LLM_BASE_URL="https://proxy.internal/v1",
            WATEREXPERT_KG_LLM_MODEL="deepseek-reasoner",
        )
        self.assertEqual(config["base_url"], "https://proxy.internal/v1")
        self.assertEqual(config["model"], "deepseek-reasoner")

    def test_bailian_aliases_still_work(self) -> None:
        config = self.config(
            DASHSCOPE_API_KEY="sk-dash",
            BAILIAN_BASE_URL="https://bailian.example/v1",
            BAILIAN_MODEL="qwen-max",
        )
        self.assertEqual(config["base_url"], "https://bailian.example/v1")
        self.assertEqual(config["model"], "qwen-max")

    def test_blank_values_are_treated_as_unset(self) -> None:
        # `.env` files ship these keys empty; an empty string must not shadow
        # the provider default.
        config = self.config(
            DEEPSEEK_API_KEY="sk-ds",
            WATEREXPERT_KG_LLM_BASE_URL="",
            WATEREXPERT_KG_LLM_MODEL="   ",
        )
        self.assertEqual(config["base_url"], "https://api.deepseek.com/v1")
        self.assertEqual(config["model"], "deepseek-chat")

    def test_is_llm_configured_tracks_the_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(kg_llm.is_llm_configured())
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-ds"}, clear=True):
            self.assertTrue(kg_llm.is_llm_configured())

    def test_missing_key_raises_with_every_accepted_name(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError) as caught:
            kg_llm.call_llm("prompt")
        message = str(caught.exception)
        for name in ("WATEREXPERT_KG_LLM_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
            self.assertIn(name, message)

    def test_config_keys_are_stable(self) -> None:
        # call_llm and is_llm_configured index this dict by name; nothing
        # unpacks it positionally, which is what made adding a key safe.
        config = self.config(DEEPSEEK_API_KEY="sk-ds")
        self.assertEqual(set(config), {"provider", "api_key", "base_url", "model"})


if __name__ == "__main__":
    unittest.main()
