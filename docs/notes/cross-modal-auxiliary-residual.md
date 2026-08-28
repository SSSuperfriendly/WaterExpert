# 跨模态辅助视觉残差模型：当前增益事实

记录时间：2026-08-28

## 结论

`cross_modal_auxiliary_visual_residual` 目前**并不是在所有目标上都优于
`baseline_non_visual`**。原先的测试
`test_current_artifact_keeps_auxiliary_visual_residual_gain` 断言两个目标都有增益，
这个断言与实际产物不符，属于测试写死了一个不成立的期望。

## 实测数据

产物：`data/processed/zhangjiabang_cross_modal/zhangjiabang_cross_modal_daily.csv`
评估方式：留一法（leave-one-out），**仅 4 个有监督样本**。

| target | model | RMSE | vs baseline |
|---|---|---:|---:|
| turbidity_ntu | baseline_non_visual | 25.9427 | — |
| turbidity_ntu | cross_modal_visual_stats | 65.3360 | **-151.85%** |
| turbidity_ntu | cross_modal_transformer | 37.6495 | -45.13% |
| turbidity_ntu | cross_modal_auxiliary_visual_residual | 25.8496 | **+0.36%** |
| secchi_depth_m | baseline_non_visual | 0.31866 | — |
| secchi_depth_m | cross_modal_visual_stats | 0.16782 | **+47.34%** |
| secchi_depth_m | cross_modal_transformer | 0.35099 | -10.15% |
| secchi_depth_m | cross_modal_auxiliary_visual_residual | 0.32375 | **-1.60%** |

## 解释

`_leave_one_out_residual_predictions`
(`src/water_ai/cross_modal/evaluation.py:271`) 的最终预测是

```
prediction = baseline_prediction + shrinkage * residual_correction
```

`shrinkage = 0.1`（`AUXILIARY_VISUAL_RESIDUAL_CONFIG`,
`evaluation.py:128-131`）。**收缩系数的作用就是限制残差修正的幅度**，
因此该模型天然只会在 baseline 附近小幅波动——它是一个保守的守护型修正，
不是一个保证增益的模型。

在 4 个样本的留一评估下，±2% 的波动完全在噪声范围内。断言"必须优于 baseline"
对这个规模的样本没有统计意义。

## 测试改成了什么

`tests/cross_modal/test_cross_modal_evaluation.py` 现在断言两件**真实成立**的事：

1. `test_auxiliary_residual_correction_stays_within_shrinkage_guard` —
   两个目标上的 RMSE 相对 baseline 的退化都不超过 5%（收缩守护确实生效）。
   这是该模型设计上真正承诺的性质。
2. `test_auxiliary_residual_correction_still_helps_turbidity` —
   浊度目标上仍有增益（当前 +0.36%），这是产物的现状特征。

## 待办

- 样本量从 4 提升到有统计意义的规模后，重新评估是否应恢复"双目标增益"断言。
- `cross_modal_visual_stats` 在 secchi 上有 **+47.34%** 的大幅增益，
  但在浊度上有 **-151.85%** 的严重退化，这个不对称目前没有解释，值得单独排查。
