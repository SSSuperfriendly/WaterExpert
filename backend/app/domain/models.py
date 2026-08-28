"""The catalogue of models a prediction job may request.

This is deliberately a plain data table rather than an import from
``scripts.pipeline.run_full_pipeline``: that module pulls in torch, matplotlib
and scikit-learn, which the API process has no reason to load. The pipeline
keeps its own ``MODEL_SPECS`` because it needs the actual classes;
``tests/pipeline/test_run_scope.py`` asserts the two stay in agreement so the
catalogue cannot drift away from what the pipeline can really run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCatalogueEntry:
    key: str
    #: i18n code the frontend resolves to a display name — never a raw label,
    #: per review item 22.
    label_code: str
    #: True when the model must run for a job's artifact chain to be complete.
    required: bool
    description_code: str


MODEL_CATALOGUE: tuple[ModelCatalogueEntry, ...] = (
    ModelCatalogueEntry(
        key="cmfbe_stgcn",
        label_code="models.cmfbe_stgcn.label",
        required=True,
        description_code="models.cmfbe_stgcn.description",
    ),
    ModelCatalogueEntry(
        key="mscim",
        label_code="models.mscim.label",
        required=False,
        description_code="models.mscim.description",
    ),
    ModelCatalogueEntry(
        key="mscim_no_kg",
        label_code="models.mscim_no_kg.label",
        required=False,
        description_code="models.mscim_no_kg.description",
    ),
)

MODEL_KEYS: tuple[str, ...] = tuple(entry.key for entry in MODEL_CATALOGUE)

#: Models every job must run: the threshold, sensitivity, counterfactual and
#: agent-context artifacts are all derived from their predictions and physics
#: coefficients, so a job that omits them can only fail at artifact validation.
REQUIRED_MODEL_KEYS: tuple[str, ...] = tuple(
    entry.key for entry in MODEL_CATALOGUE if entry.required
)

BASELINE_KEYS: tuple[str, ...] = ("ridge_window_baseline", "persistence_baseline")


def is_known_model(key: str) -> bool:
    return key in MODEL_KEYS


def models_for_request(requested: str | None) -> list[str]:
    """The full model list a job must run to satisfy ``requested``.

    The requested model comes first — it is the one the job reports on — and the
    required models follow so the downstream artifact chain can be built.
    """
    enabled = [requested] if requested else []
    enabled.extend(key for key in REQUIRED_MODEL_KEYS if key not in enabled)
    return enabled
