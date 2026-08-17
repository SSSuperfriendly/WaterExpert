from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.cross_modal.evaluation import evaluate_cross_modal_models
from water_ai.vision import extract_visual_transformer_features


class VisionFeatureTest(unittest.TestCase):
    def test_transformer_features_are_deterministic_and_complete(self) -> None:
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        image[:, :, 0] = 80
        image[:, :, 1] = 120
        image[:, :, 2] = 160

        first = extract_visual_transformer_features(image)
        second = extract_visual_transformer_features(image)

        embedding_keys = [
            key for key in first if re.fullmatch(r"visual_transformer_embedding_\d{2}", key)
        ]
        self.assertEqual(len(embedding_keys), 32)
        self.assertEqual(first["visual_transformer_embed_dim"], 32)
        self.assertEqual(first["visual_transformer_patch_count"], 16)
        self.assertAlmostEqual(
            first["visual_transformer_embedding_norm"],
            second["visual_transformer_embedding_norm"],
            places=8,
        )


class CrossModalEvaluationTest(unittest.TestCase):
    def test_evaluation_returns_three_model_variants_for_each_target(self) -> None:
        df = pd.DataFrame(
            {
                "sample_date": ["2026-07-06", "2026-07-13", "2026-07-21", "2026-07-28"],
                "field_sample_date": ["2026-07-13", "2026-07-13", "2026-07-21", "2026-08-03"],
                "has_field_monitoring_label": [True, True, True, True],
                "label_alignment": [
                    "same_week_context",
                    "exact_same_day",
                    "exact_same_day",
                    "same_week_context",
                ],
                "fusion_readiness": [
                    "weak_temporal_context_cross_modal_sample",
                    "strong_supervised_cross_modal_sample",
                    "strong_supervised_cross_modal_sample",
                    "weak_temporal_context_cross_modal_sample",
                ],
                "turbidity_ntu": [87.6, 87.6, 179.3333, 162.0],
                "secchi_depth_m": [0.4733, 0.4733, 0.2217, 0.315],
                "uav_asset_count": [2, 1, 2, 2],
                "uav_image_count": [1, 0, 1, 1],
                "uav_video_count": [1, 1, 1, 1],
                "uav_turbidity_visual_proxy_mean": [0.118, 0.051, 0.064, 0.075],
                "uav_sharpness_laplacian_mean": [402.0, 27.2, 255.8, 223.1],
                "uav_visual_transformer_embedding_01_mean": [0.1, 0.2, 0.3, 0.4],
                "uav_visual_transformer_embedding_02_mean": [0.2, 0.1, 0.4, 0.3],
            }
        )

        metrics, predictions = evaluate_cross_modal_models(df)

        self.assertEqual(set(metrics["target"]), {"turbidity_ntu", "secchi_depth_m"})
        self.assertEqual(
            set(metrics["model_name"]),
            {
                "baseline_non_visual",
                "cross_modal_visual_stats",
                "cross_modal_transformer",
            },
        )
        self.assertEqual(len(metrics), 6)
        self.assertEqual(len(predictions), 24)
        self.assertIn("rmse_reduction_pct_vs_baseline", metrics.columns)

        for target in ("turbidity_ntu", "secchi_depth_m"):
            target_metrics = metrics.set_index(["target", "model_name"]).loc[target]
            baseline_rmse = target_metrics.loc["baseline_non_visual", "rmse"]
            transformer_rmse = target_metrics.loc["cross_modal_transformer", "rmse"]
            self.assertLess(transformer_rmse, baseline_rmse)
            self.assertGreater(
                target_metrics.loc[
                    "cross_modal_transformer", "rmse_reduction_pct_vs_baseline"
                ],
                0.0,
            )


if __name__ == "__main__":
    unittest.main()
