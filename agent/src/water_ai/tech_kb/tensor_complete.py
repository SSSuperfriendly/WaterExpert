from __future__ import annotations

from pathlib import Path

import numpy as np


def _normalize01(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values, dtype=float)
    lo = float(finite.min())
    hi = float(finite.max())
    if hi <= lo:
        return np.zeros_like(values, dtype=float)
    return (values - lo) / (hi - lo)


def _mode_unfold(tensor: np.ndarray, mode: int) -> np.ndarray:
    moved = np.moveaxis(tensor, mode, 0)
    return moved.reshape(tensor.shape[mode], -1)


def _mode_fold(matrix: np.ndarray, shape: tuple[int, ...], mode: int) -> np.ndarray:
    full_shape = (shape[mode],) + tuple(dim for idx, dim in enumerate(shape) if idx != mode)
    tensor = matrix.reshape(full_shape)
    return np.moveaxis(tensor, 0, mode)


def low_rank_complete(
    observed: np.ndarray,
    mask: np.ndarray,
    rank: int = 4,
    max_iter: int = 50,
    tol: float = 1e-5,
) -> np.ndarray:
    """Complete a partially observed tensor with iterative low-rank SVD updates."""
    if observed.shape != mask.shape:
        raise ValueError("observed and mask must have the same shape")
    if observed.ndim < 2:
        raise ValueError("tensor completion expects at least two dimensions")

    observed = observed.astype(float, copy=False)
    mask = mask.astype(bool, copy=False)
    if mask.any():
        fill_value = float(observed[mask].mean())
    else:
        fill_value = 0.0

    completed = np.where(mask, observed, fill_value)
    rank = max(1, min(rank, min(observed.shape)))

    for _ in range(max_iter):
        previous = completed.copy()
        estimates = []
        for mode in range(completed.ndim):
            unfolded = _mode_unfold(completed, mode)
            u, s, vt = np.linalg.svd(unfolded, full_matrices=False)
            kept = min(rank, s.size)
            approx = (u[:, :kept] * s[:kept]) @ vt[:kept, :]
            estimates.append(_mode_fold(approx, completed.shape, mode))
        completed = np.mean(estimates, axis=0)
        completed[mask] = observed[mask]
        delta = np.linalg.norm(completed - previous)
        scale = np.linalg.norm(previous) + 1e-12
        if delta / scale < tol:
            break

    return np.clip(completed, 0.0, 1.0)


class TensorCompletion:
    def __init__(
        self,
        tensor_path: str | Path,
        rank: int = 4,
        max_iter: int = 50,
        tol: float = 1e-5,
    ) -> None:
        self.tensor_path = Path(tensor_path)
        self.rank = rank
        self.max_iter = max_iter
        self.tol = tol

    def load(self) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
        if not self.tensor_path.exists():
            raise FileNotFoundError(f"Tensor file not found: {self.tensor_path}")

        with np.load(self.tensor_path, allow_pickle=False) as data:
            tensor_key = "observed_tensor" if "observed_tensor" in data else "tensor"
            if tensor_key not in data:
                raise KeyError(f"{self.tensor_path} does not contain an observed tensor")
            observed = data[tensor_key].astype(float)
            if "mask" in data:
                mask = data["mask"].astype(bool)
            else:
                mask = np.isfinite(observed)
            reserved = {
                "observed_tensor",
                "tensor",
                "mask",
                "completed_tensor",
                "completion_rank",
                "completion_max_iter",
            }
            metadata = {key: data[key] for key in data.files if key not in reserved}
        return observed, mask, metadata

    def complete(self, mask: np.ndarray | None = None, observed: np.ndarray | None = None) -> np.ndarray:
        if observed is None:
            observed, loaded_mask, _ = self.load()
            mask = loaded_mask if mask is None else mask
        if mask is None:
            mask = np.isfinite(observed)
        return low_rank_complete(
            observed=np.nan_to_num(observed, nan=0.0),
            mask=mask,
            rank=self.rank,
            max_iter=self.max_iter,
            tol=self.tol,
        )

    def save_completed(self, output_path: str | Path | None = None) -> Path:
        observed, mask, metadata = self.load()
        completed = self.complete(mask=mask, observed=observed)
        path = Path(output_path) if output_path is not None else self.tensor_path
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            observed_tensor=observed,
            completed_tensor=completed,
            tensor=completed,
            mask=mask.astype(np.uint8),
            completion_rank=np.array(self.rank, dtype=np.int32),
            completion_max_iter=np.array(self.max_iter, dtype=np.int32),
            **metadata,
        )
        return path
