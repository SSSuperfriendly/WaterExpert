import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from water_ai.tech_kb.kg_builder import KnowledgeGraphBuilder
from water_ai.tech_kb.tensor_complete import TensorCompletion, low_rank_complete


class TestTechKB(unittest.TestCase):
    def test_load_seed_data(self):
        builder = KnowledgeGraphBuilder("data/tech_knowledge_base/tech_quadruples.jsonl")
        triples = builder.build()
        self.assertIsInstance(triples, list)
        self.assertGreaterEqual(len(triples), 1)

    def test_tensor_completion_preserves_observed_entries(self):
        observed = np.zeros((2, 2, 2, 2), dtype=float)
        mask = np.zeros_like(observed, dtype=bool)
        observed[0, 0, :, 0] = [0.8, 0.4]
        observed[1, 1, :, 1] = [0.2, 0.9]
        mask[0, 0, :, 0] = True
        mask[1, 1, :, 1] = True

        completed = low_rank_complete(observed, mask, rank=2, max_iter=5)

        self.assertEqual(completed.shape, observed.shape)
        self.assertTrue(np.allclose(completed[mask], observed[mask]))
        self.assertGreaterEqual(float(completed.min()), 0.0)
        self.assertLessEqual(float(completed.max()), 1.0)

    def test_tensor_completion_saves_expected_npz_fields(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tensor.npz"
            observed = np.zeros((1, 1, 2, 1), dtype=float)
            mask = np.ones_like(observed, dtype=np.uint8)
            np.savez_compressed(path, observed_tensor=observed, mask=mask, technologies=np.array(["a"]))

            saved = TensorCompletion(path, rank=1, max_iter=2).save_completed()

            with np.load(saved, allow_pickle=False) as data:
                self.assertIn("observed_tensor", data.files)
                self.assertIn("completed_tensor", data.files)
                self.assertIn("tensor", data.files)
                self.assertIn("mask", data.files)
                self.assertIn("technologies", data.files)


if __name__ == "__main__":
    unittest.main()
