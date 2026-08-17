# 张家浜跨模态模型前后对比

## 评估入口

```powershell
.\.ai4s\Scripts\python.exe scripts\analysis\evaluate_zhangjiabang_cross_modal_models.py
```

## 落库产物

- `data/processed/zhangjiabang_cross_modal/cross_modal_model_comparison.csv`
- `data/processed/zhangjiabang_cross_modal/cross_modal_model_predictions.csv`
- `data/processed/zhangjiabang_cross_modal/cross_modal_model_comparison.json`

## 对比方案

| 方案 | 含义 |
| --- | --- |
| `baseline_non_visual` | 加入跨模态前：只使用日期上下文和可用代理气象字段。 |
| `cross_modal_visual_stats` | 加入可解释 UAV 视觉特征后：亮度、饱和度、棕黄浊度代理、反光、暗水面、清晰度等。 |
| `cross_modal_transformer` | 加入 Transformer 视觉表征后：可解释视觉特征 + 32 维视觉 Transformer embedding。 |

当前监督样本只有 4 行，因此采用留一法交叉验证。这个结果是小样本工程检验，不是生产级泛化评估。

## 当前结论

当前张家浜样本上，加入跨模态特征后尚未带来模型性能提升。

| 目标 | 当前最佳方案 | 最佳 RMSE | 最佳成功率 |
| --- | --- | ---: | ---: |
| 浊度 | `baseline_non_visual` | 37.49 NTU | 50.0% |
| 透明度 | `baseline_non_visual` | 0.121 m | 50.0% |

这说明目前跨模态工程链路已经打通，但视觉分支还没有形成稳定收益。主要原因不是接口或数据落库问题，而是监督样本过少、视觉 Transformer 尚未用水体任务训练、弱监督样本存在日期偏移。后续新增同日 UAV 和实测标签后，应复跑本脚本，并以该产物作为是否真正提升模型的判断依据。
