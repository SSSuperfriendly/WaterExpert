# Cross-Modal Module Architecture

## Layering

The Zhangjiabang cross-modal work is now split into reusable product layers instead of one-off scripts.

| Layer | Location | Responsibility |
| --- | --- | --- |
| Vision feature core | `src/water_ai/vision/` | Offline visual Transformer feature extraction for UAV images and sampled video frames. |
| Cross-modal evaluation core | `src/water_ai/cross_modal/` | Before/after model comparison using the same supervised Zhangjiabang rows. |
| Preprocess entrypoint | `scripts/preprocess/build_zhangjiabang_cross_modal_dataset.py` | Parse field monitoring Excel, index UAV media, generate thumbnails/frames, build daily fusion tables. |
| Evaluation entrypoint | `scripts/analysis/evaluate_zhangjiabang_cross_modal_models.py` | Thin CLI wrapper around the reusable evaluation core. |
| Service layer | `backend/app/services/cross_modal_repository.py` | Read processed cross-modal artifacts and expose API-ready DTOs. |
| Application layer | `frontend/visualization.html`, `frontend/js/visualization.js` | Display cross-modal counts, media previews, daily fusion rows, and model before/after metrics. |

## Artifacts

Processed artifacts live under `data/processed/zhangjiabang_cross_modal/`.

- `uav_asset_index.csv`: per-image/video asset metadata, visual statistics, Transformer embeddings, preview paths.
- `uav_visual_daily_features.csv`: date-level UAV visual feature aggregation.
- `zhangjiabang_cross_modal_daily.csv`: date-level fusion of UAV features and field monitoring labels.
- `cross_modal_model_comparison.csv`: metric table for baseline vs cross-modal variants.
- `cross_modal_model_predictions.csv`: leave-one-out prediction records.
- `cross_modal_model_comparison.json`: API-ready evaluation summary.

## Guardrails

- Raw UAV videos stay outside git; only lightweight processed previews and tabular artifacts are committed.
- The current evaluation is a small-sample engineering comparison, not a production-grade retraining benchmark.
- The current best-performing Zhangjiabang variant is nearby-river visual residual correction. It evaluates only Zhangjiabang target rows while allowing Chenxing/Sanlu River UAV rows to support the visual residual branch.
- Historical proxy context from Sanjiagang `2198` and Pudong `58370` is treated as non-visual context, not as direct Zhangjiabang measurements.
- Directly concatenating many visual features is still rejected by the comparison: it overfits the tiny supervised set and performs worse than the non-visual baseline.
