"""The model registry: models as governed, versioned assets (review item 11).

Before this, the overview page showed "the best model" by reading test-set
metrics out of a checked-in artifact. A model was never a *thing*: it had no
version, no approver, no record of which training data produced it, and no
"which one is actually serving predictions right now" answer.

A :class:`ModelService` turns a trained model into a registry entry with a
lifecycle (实验 → 候选 → 审核 → 发布 → 退役). Publishing a version makes it the
default for its ``model_key`` and retires the previous default, so there is
always exactly one published model per key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.domain.codes import ErrorCode, ModelStage
from backend.app.services.state_store import MODEL_REGISTRY_TABLE, SqliteStateStore
from backend.app.services.upload_guard import UploadRejected

ID_LENGTH = 12

#: Which stages may follow which, as a directed graph.
MODEL_TRANSITIONS: dict[str, set[str]] = {
    ModelStage.EXPERIMENT: {ModelStage.CANDIDATE, ModelStage.RETIRED},
    ModelStage.CANDIDATE: {ModelStage.IN_REVIEW, ModelStage.RETIRED},
    ModelStage.IN_REVIEW: {ModelStage.PUBLISHED, ModelStage.CANDIDATE, ModelStage.RETIRED},
    ModelStage.PUBLISHED: {ModelStage.RETIRED},
    ModelStage.RETIRED: set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ModelNotFound(KeyError):
    """No registered model version with that id."""


class ModelService:
    def __init__(self, store: SqliteStateStore) -> None:
        self.store = store

    # -- creation ------------------------------------------------------------

    def register(
        self,
        *,
        model_key: str,
        version: str,
        author: str,
        station_code: str | None = None,
        training_dataset_version_id: str | None = None,
        config_hash: str | None = None,
        metrics: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Register a model version at the ``experiment`` stage."""
        timestamp = utc_now()
        record = {
            "model_version_id": uuid4().hex[:ID_LENGTH],
            "created_at": timestamp,
            "updated_at": timestamp,
            "model_key": model_key.strip(),
            "version": version.strip(),
            "stage": str(ModelStage.EXPERIMENT),
            "station_code": station_code,
            "training_dataset_version_id": training_dataset_version_id,
            "config_hash": config_hash,
            "metrics": metrics or {},
            "author": author,
            "published_at": None,
            "retired_at": None,
            "notes": notes,
        }
        return self.store.insert(MODEL_REGISTRY_TABLE, record)

    # -- reads ---------------------------------------------------------------

    def get(self, model_version_id: str) -> dict[str, Any]:
        model = self.store.get(MODEL_REGISTRY_TABLE, model_version_id)
        if model is None:
            raise ModelNotFound(model_version_id)
        return model

    def list(
        self,
        *,
        model_key: str | None = None,
        stage: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if model_key:
            filters["model_key"] = model_key
        if stage:
            filters["stage"] = stage
        return self.store.list(MODEL_REGISTRY_TABLE, filters=filters or None, limit=limit)

    def current(self, model_key: str | None = None) -> dict[str, Any] | None:
        """The published model serving predictions for a key (all keys if none).

        The overview page answers "what is running right now" from here, not
        from a static "best model" block (review item 12).
        """
        published = [
            model
            for model in self.store.list(MODEL_REGISTRY_TABLE, filters={"stage": str(ModelStage.PUBLISHED)})
            if not model_key or model.get("model_key") == model_key
        ]
        if not published:
            return None
        # One published model per key; newest wins as a tie-break.
        return sorted(published, key=lambda m: str(m.get("published_at") or ""), reverse=True)[0]

    # -- lifecycle -----------------------------------------------------------

    def transition(self, model_version_id: str, to_stage: str, actor: str) -> dict[str, Any]:
        """Move a model along its lifecycle, enforcing the transition graph."""
        model = self.get(model_version_id)
        current = str(model.get("stage", ModelStage.EXPERIMENT))
        if to_stage not in MODEL_TRANSITIONS.get(current, set()):
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot move model from {current} to {to_stage}.",
            )
        updates: dict[str, Any] = {"stage": to_stage, "updated_at": utc_now()}
        if to_stage == str(ModelStage.PUBLISHED):
            updates["published_at"] = utc_now()
            updates["published_by"] = actor
            self._retire_previous_defaults(str(model["model_key"]), keep=model_version_id)
        elif to_stage == str(ModelStage.RETIRED):
            updates["retired_at"] = utc_now()
            updates["retired_by"] = actor
        return self.store.update(MODEL_REGISTRY_TABLE, model_version_id, updates)

    def _retire_previous_defaults(self, model_key: str, keep: str) -> None:
        """A new publish supersedes the previous default for the same key."""
        for model in self.store.list(MODEL_REGISTRY_TABLE, filters={"model_key": model_key}):
            if str(model["model_version_id"]) == keep:
                continue
            if str(model.get("stage")) == str(ModelStage.PUBLISHED):
                self.store.update(
                    MODEL_REGISTRY_TABLE,
                    str(model["model_version_id"]),
                    {"stage": str(ModelStage.RETIRED), "retired_at": utc_now()},
                )

    def summary(self) -> dict[str, Any]:
        """Published-model count and per-key current version (operational home)."""
        models = self.store.list(MODEL_REGISTRY_TABLE)
        by_stage: dict[str, int] = {}
        current: dict[str, str] = {}
        for model in models:
            stage = str(model.get("stage", ModelStage.EXPERIMENT))
            by_stage[stage] = by_stage.get(stage, 0) + 1
            if stage == str(ModelStage.PUBLISHED):
                key = str(model.get("model_key", "unknown"))
                current[key] = str(model.get("version", ""))
        return {
            "total": len(models),
            "by_stage": by_stage,
            "published": by_stage.get(str(ModelStage.PUBLISHED), 0),
            "current_by_key": current,
        }
