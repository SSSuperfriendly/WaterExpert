import unittest
from unittest.mock import patch

from water_ai.llm.deepseek_client import DeepSeekClient


class TestLLM(unittest.TestCase):
    def test_deepseek_local_backend(self):
        client = DeepSeekClient(config={"backend": "local", "local": {"model_path": "local_deepseek_model"}})
        response = client.generate("测试提示")
        self.assertEqual(response["backend"], "local")
        self.assertIn("prompt", response)

    def test_api_backend_reads_deepseek_key_from_env(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=False):
            client = DeepSeekClient(config={"backend": "api"})

        self.assertEqual(client.backend.api_key, "sk-test")


if __name__ == "__main__":
    unittest.main()
