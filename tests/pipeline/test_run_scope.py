"""The pipeline must honour the model/date/station a job asks for.

Review item 1: the UI let users pick a model, a date range and a station, but the
pipeline hardcoded three models and derived the date range from whatever the data
happened to contain. These tests pin the rule that a requested parameter either
takes effect or is refused — never silently ignored.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.domain.models import (
    BASELINE_KEYS,
    MODEL_KEYS,
    models_for_request,
)
from backend.app.domain.models import REQUIRED_MODEL_KEYS as CATALOGUE_REQUIRED
from scripts.pipeline.run_full_pipeline import (
    DEFAULT_ENABLED_BASELINES,
    DEFAULT_ENABLED_MODELS,
    MIN_SCOPED_ROWS,
    MODEL_SPECS,
    REQUIRED_MODEL_KEYS,
    RunScopeError,
    apply_run_scope,
    resolve_enabled_baselines,
    resolve_enabled_models,
    resolve_water_pattern,
)


def _dataset(days: int = 120) -> tuple[pd.DataFrame, dict]:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=days, freq="D"),
            "turbidity": np.linspace(5.0, 95.0, days),
        }
    )
    summary = {
        "feature_columns": ["turbidity"],
        "rows_after_merge": days,
        "date_range": {
            "start": str(frame["date"].min().date()),
            "end": str(frame["date"].max().date()),
        },
        "clearness_transform": {"log_turbidity_min": 0.0, "log_turbidity_max": 99.0},
    }
    return frame, summary


class ModelSelectionTest(unittest.TestCase):
    def test_default_selection_is_the_historic_three_models(self) -> None:
        self.assertEqual(resolve_enabled_models({}), list(DEFAULT_ENABLED_MODELS))
        self.assertEqual(resolve_enabled_baselines({}), list(DEFAULT_ENABLED_BASELINES))

    def test_a_subset_is_honoured_in_the_requested_order(self) -> None:
        selected = resolve_enabled_models(
            {"models": {"enabled": ["cmfbe_stgcn", "mscim"]}}
        )
        self.assertEqual(selected, ["cmfbe_stgcn", "mscim"])

    def test_a_single_name_is_accepted(self) -> None:
        self.assertEqual(
            resolve_enabled_models({"models": {"enabled": "cmfbe_stgcn"}}), ["cmfbe_stgcn"]
        )

    def test_duplicates_collapse(self) -> None:
        selected = resolve_enabled_models(
            {"models": {"enabled": ["cmfbe_stgcn", "cmfbe_stgcn"]}}
        )
        self.assertEqual(selected, ["cmfbe_stgcn"])

    def test_dropping_cmfbe_is_refused_because_artifacts_depend_on_it(self) -> None:
        """Otherwise the run trains fine and then fails at artifact validation."""
        with self.assertRaises(RunScopeError) as ctx:
            resolve_enabled_models({"models": {"enabled": ["mscim", "mscim_no_kg"]}})
        self.assertIn("cmfbe_stgcn", str(ctx.exception))

    def test_the_default_selection_satisfies_the_required_models(self) -> None:
        self.assertTrue(set(REQUIRED_MODEL_KEYS).issubset(DEFAULT_ENABLED_MODELS))

    def test_an_unknown_model_is_refused_rather_than_skipped(self) -> None:
        with self.assertRaises(RunScopeError) as ctx:
            resolve_enabled_models({"models": {"enabled": ["mscim", "transformer_xl"]}})
        self.assertIn("transformer_xl", str(ctx.exception))

    def test_an_empty_selection_is_refused(self) -> None:
        with self.assertRaises(RunScopeError):
            resolve_enabled_models({"models": {"enabled": []}})

    def test_a_non_list_selection_is_refused(self) -> None:
        with self.assertRaises(RunScopeError):
            resolve_enabled_models({"models": {"enabled": {"mscim": True}}})

    def test_every_spec_declares_a_distinct_risk_weight_key(self) -> None:
        keys = [spec.risk_weight_key for spec in MODEL_SPECS.values()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_only_cmfbe_trains_with_the_physics_term(self) -> None:
        physics = {name for name, spec in MODEL_SPECS.items() if spec.include_physics}
        self.assertEqual(physics, {"cmfbe_stgcn"})

    def test_the_no_kg_ablation_is_the_only_one_without_graph_priors(self) -> None:
        without = {name for name, spec in MODEL_SPECS.items() if not spec.use_kg_adjacency}
        self.assertEqual(without, {"mscim_no_kg"})


class CatalogueAgreementTest(unittest.TestCase):
    """The API's model catalogue must describe what the pipeline can really run.

    ``backend/app/domain/models.py`` deliberately does not import this module —
    the API process should not load torch — so the two lists can only be kept
    honest by asserting they agree.
    """

    def test_the_backend_catalogue_lists_exactly_the_pipeline_models(self) -> None:
        self.assertEqual(set(MODEL_KEYS), set(MODEL_SPECS))

    def test_the_required_model_sets_agree(self) -> None:
        self.assertEqual(set(CATALOGUE_REQUIRED), set(REQUIRED_MODEL_KEYS))

    def test_the_backend_baselines_are_the_pipeline_baselines(self) -> None:
        self.assertEqual(set(BASELINE_KEYS), set(DEFAULT_ENABLED_BASELINES))

    def test_models_for_request_always_satisfies_the_pipeline(self) -> None:
        """Whatever the UI asks for, the resulting selection must be runnable."""
        for requested in MODEL_KEYS:
            with self.subTest(model=requested):
                enabled = models_for_request(requested)
                self.assertEqual(enabled[0], requested)
                self.assertEqual(
                    resolve_enabled_models({"models": {"enabled": enabled}}), enabled
                )


class WaterPatternTest(unittest.TestCase):
    def test_a_placeholder_pattern_is_filled_with_the_station_code(self) -> None:
        resolved = resolve_water_pattern(
            {"water_pattern": "wq_{station_code}.csv", "run_scope": {"station_code": "4001"}}
        )
        self.assertEqual(resolved, "wq_4001.csv")

    def test_a_fixed_filename_matching_the_station_is_kept(self) -> None:
        resolved = resolve_water_pattern(
            {
                "water_pattern": "wusongkou_water_quality_2586.csv",
                "run_scope": {"station_code": "2586"},
            }
        )
        self.assertEqual(resolved, "wusongkou_water_quality_2586.csv")

    def test_a_station_that_does_not_match_the_filename_is_refused(self) -> None:
        """Otherwise a request for station 4001 would train on station 2586's file."""
        with self.assertRaises(RunScopeError) as ctx:
            resolve_water_pattern(
                {
                    "water_pattern": "wusongkou_water_quality_2586.csv",
                    "run_scope": {"station_code": "4001"},
                }
            )
        self.assertIn("4001", str(ctx.exception))

    def test_no_station_code_leaves_the_pattern_untouched(self) -> None:
        self.assertEqual(resolve_water_pattern({"water_pattern": "anything.csv"}), "anything.csv")


class RunScopeTest(unittest.TestCase):
    def test_an_absent_scope_passes_the_dataset_through_unchanged(self) -> None:
        frame, summary = _dataset()
        scoped, scoped_summary, report = apply_run_scope(frame, summary, {})

        self.assertFalse(report["applied"])
        self.assertEqual(len(scoped), len(frame))
        self.assertIs(scoped_summary, summary)
        self.assertEqual(report["effective_start_date"], "2024-01-01")

    def test_the_date_range_is_clipped_inclusively(self) -> None:
        frame, summary = _dataset()
        scoped, scoped_summary, report = apply_run_scope(
            frame,
            summary,
            {"run_scope": {"start_date": "2024-02-01", "end_date": "2024-03-31"}},
        )

        self.assertTrue(report["applied"])
        self.assertEqual(len(scoped), 60)
        self.assertEqual(report["effective_start_date"], "2024-02-01")
        self.assertEqual(report["effective_end_date"], "2024-03-31")
        self.assertEqual(scoped_summary["rows_after_merge"], 60)
        self.assertEqual(scoped_summary["date_range"]["start"], "2024-02-01")

    def test_the_clearness_transform_is_recomputed_for_the_scoped_rows(self) -> None:
        """It normalises the model's clearness target, so it must match the rows used."""
        frame, summary = _dataset()
        _, scoped_summary, _ = apply_run_scope(
            frame, summary, {"run_scope": {"start_date": "2024-02-01"}}
        )

        transform = scoped_summary["clearness_transform"]
        self.assertNotEqual(transform, summary["clearness_transform"])
        self.assertAlmostEqual(
            transform["log_turbidity_max"],
            float(np.log1p(frame["turbidity"].max())),
        )
        self.assertGreater(transform["log_turbidity_min"], 0.0)

    def test_a_range_outside_the_data_is_refused_before_training(self) -> None:
        frame, summary = _dataset()
        with self.assertRaises(RunScopeError) as ctx:
            apply_run_scope(
                frame, summary, {"run_scope": {"start_date": "2030-01-01"}}
            )
        message = str(ctx.exception)
        self.assertIn("2024-01-01", message)  # tells the caller what is available
        self.assertIn(str(MIN_SCOPED_ROWS), message)

    def test_a_malformed_date_is_refused(self) -> None:
        frame, summary = _dataset()
        with self.assertRaises(RunScopeError):
            apply_run_scope(frame, summary, {"run_scope": {"start_date": "last tuesday"}})

    def test_the_report_records_both_requested_and_effective_bounds(self) -> None:
        frame, summary = _dataset()
        _, _, report = apply_run_scope(
            frame,
            summary,
            {"run_scope": {"station_code": "2586", "start_date": "2024-01-15"}},
        )

        self.assertEqual(report["station_code"], "2586")
        self.assertEqual(report["requested_start_date"], "2024-01-15")
        self.assertIsNone(report["requested_end_date"])
        self.assertEqual(report["effective_start_date"], "2024-01-15")
        self.assertEqual(report["effective_end_date"], "2024-04-29")
        self.assertEqual(report["rows_before_scope"], 120)
        self.assertEqual(report["rows_after_scope"], 106)


if __name__ == "__main__":
    unittest.main()
