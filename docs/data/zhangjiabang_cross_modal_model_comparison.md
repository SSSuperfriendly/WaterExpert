# 张家浜跨模态模型前后对比

## 评估入口

```powershell
.\.ai4s\Scripts\python.exe scripts\analysis\evaluate_zhangjiabang_cross_modal_models.py
```

## 落库产物

- `data/processed/zhangjiabang_cross_modal/cross_modal_model_comparison.csv`
- `data/processed/zhangjiabang_cross_modal/cross_modal_model_predictions.csv`
- `data/processed/zhangjiabang_cross_modal/cross_modal_model_comparison.json`

## 当前数据口径

- 目标评估样本：张家浜目标样本 `4` 行。
- 辅助训练样本：陈行基地旁三鲁河段 `2` 行，只进入跨模态残差训练池，不进入张家浜评估集。
- 代理历史上下文：张家浜东闸站使用三甲港 `2198` 水质代理站和浦东 `58370` 气象站，按同月上/中/下旬聚合历史中位数和 IQR。
- 验证方式：目标样本留一验证。该结果仍是小样本工程检验，不是生产级泛化评估。

## 对比方案

| 方案 | 含义 |
| --- | --- |
| `baseline_non_visual` | 加入跨模态前：日期上下文 + 2198/58370 历史同月代理特征。 |
| `cross_modal_visual_stats` | 直接拼接 UAV 可解释视觉统计特征。当前小样本下容易过拟合。 |
| `cross_modal_transformer` | Transformer 视觉表征残差融合。当前在更强历史代理 baseline 下未成为最优。 |
| `cross_modal_auxiliary_visual_residual` | 张家浜作为评估目标，三鲁河段作为相近河段辅助样本，UAV 视觉统计只做保守残差校正。 |

## 当前结论

在加入 2198/58370 历史代理特征后，非视觉 baseline 已明显增强；在这个更强 baseline 上，`cross_modal_auxiliary_visual_residual` 仍带来小幅正收益。

| 目标 | 加入跨模态前 RMSE | 最优跨模态方案 | 跨模态后 RMSE | RMSE 降低 |
| --- | ---: | --- | ---: | ---: |
| 浊度 | `25.9427 NTU` | `cross_modal_auxiliary_visual_residual` | `25.8496 NTU` | `0.36%` |
| 透明度 | `0.095851 m` | `cross_modal_auxiliary_visual_residual` | `0.095618 m` | `0.24%` |

这说明新增数据的主要贡献有两层：历史代理站让非视觉上下文更强，三鲁河段 UAV/实测样本让视觉残差校正在强 baseline 上仍有可复跑的正向收益。由于监督样本仍很少，当前结论应表述为“小样本工程验证中出现提升”，不能表述为生产级泛化能力已经充分验证。
