# Water AI Agent —— 本地部署运行手册

> 合作方的 Water AI Multi-Agent 推理 API（此前经 Cloudflare 临时隧道接入，会随
> `cloudflared` 重启而失效）现已**完整部署到本机**，平台默认直连本地 `127.0.0.1:8001`，
> 不再依赖外部隧道。本文档说明部署目录、启动/重启、验证与升级方式。

> **2026-09-09 整合**：agent 已并入平台仓库为子目录 `agent/`
> （即 `/Users/mac/Project/WaterExpert/agent`），原独立目录
> `/Users/mac/Project/agent-water-expert` 已合并后删除——**整个项目只有
> `/Users/mac/Project/WaterExpert/` 一个路径**。源码随仓库跟踪；`agent/data`、
> `agent/outputs`、`agent/.venv`、`agent/.env`、`agent/.swap_backup_*/` 为本地产物
> （gitignored，随发布 rsync 上服务器）。

---

## 1. 状态与拓扑

| 项 | 值 |
| --- | --- |
| 部署目录 | `/Users/mac/Project/WaterExpert/agent`（仓库子目录；2026-09-09 由原独立目录 `/Users/mac/Project/agent-water-expert` 整体并入） |
| 运行端口 | `127.0.0.1:8001`（避开平台后端 `:8000`；平台与 agent 同机共存） |
| Python | py3.12 venv：`.venv/`（uv 创建，API 运行时依赖已装） |
| 平台默认指向 | `WATEREXPERT_AGENT_API_URL` 未设时 → `http://127.0.0.1:8001/api` |
| 模型核心 | 已换为我方新版 MSCIM/CMFBE（代码+权重，见第 8 节；合作方原版备份于 `.swap_backup_20260908/`） |
| 已接入接口 | `health / status / scenarios / strategy / strategy/{job_id} / explain / stage / jobs` |
| 2026-09-08 验证 | 6 agent 全 ready；4 场景 strategy 均 completed（~3s/个）；explain 命中案例库 |

平台后端（FastAPI :8000）只做 httpx 反向代理（`backend/app/services/external_agent.py`），
浏览器永不直接访问 agent；agent 宕机 → 平台返回 502 `agent_unavailable`，前端本地化提示。

## 2. 目录是如何组装的（复现/审计用）

部署树来历 = **GitHub 快照 `git@github.com:vvvlun/agent-water-expert.git`**（2026-09-02，
含 src/water_ai、configs、scripts、docs 等）+ 覆盖合作方**实际运行目录**的三份内容
（与源码快照的差异正对应此前启动缺失项）。该组装树已于 2026-09-09 并入本仓库
`agent/` 子目录（源码进 git；`data/`、`outputs/`、`.venv`、`.env`、`.swap_backup_*/`
gitignored 但保留在磁盘）。

> 三份 zip（`src_data.zip` / `案例库_data.zip` / `outputs.zip`，原在仓库根下）已于
> 2026-09-09 就地解压归档到 `WaterExpert/archive/2026-09-09-backup/` 后删除（见该目录
> README：74 个文件、1:1 校验）。重建部署树时从归档目录取对应内容即可：

| 归档子目录 | 落到部署目录的何处 | 提供内容 |
| --- | --- | --- |
| `from-src_data/` | `src/water_ai/data/` | `loader.py` 等数据加载源码包（此前缺失 → 启动崩溃根因） |
| `from-case_library_data/` | `data/` | 相似案例库、全站点数据库（补充清单）、知识图谱、tech 知识库 |
| `from-outputs.zip/` | `outputs/` | RL 策略 checkpoints/回放缓冲、pareto 结果、场景 s1–s4 数据与报告、api_jobs 审计留档 |

权重 md5。**当前激活的是我方新版模型核心（2026-09-08 换芯）**，合作方原版与换芯前代码备份在
`.swap_backup_20260908/`：

```
# 现激活（我方研究仓 8-19 版本，代码 + 权重同源）
outputs/models/mscim.pt        = abbfd68c72420d70f054888d97541a4d
outputs/models/cmfbe_stgcn.pt  = e1c7dab6ffb48e0386a11457a32637e9
outputs/models/mscim_no_kg.pt  = 300e6c020dae04fbde8d7e3b6e3e34d1
# 备份（合作方 5-23 精简版）
outputs/models/mscim.pt        = 442ee7a491e12526de94e97a35af43a2
outputs/models/cmfbe_stgcn.pt  = 6e553a9386e4b8e857770f112ca76d7f
outputs/models/mscim_no_kg.pt  = a3ce7ac02b9d672e4b4640e7e5c56b7a
```

> 若部署目录需在另一台机器重建：clone 上述 GitHub 仓库 → 同法解压三份 zip 到对应位置 →
> 建 venv 装 `requirements-api.txt` 即可（`tigramite`/`vllm` 仅训练侧需要，API 启动不依赖）。
> 重建后如需复现换芯，按第 8 节操作。

## 3. 启动 / 重启

```bash
cd /Users/mac/Project/WaterExpert/agent

# 前台运行（联调看日志）
.venv/bin/python scripts/run_api_server.py --host 127.0.0.1 --port 8001

# 后台常驻（本机重启后需重新拉起；会话内用的方式）
nohup .venv/bin/python scripts/run_api_server.py --host 127.0.0.1 --port 8001 \
    > /tmp/water_ai_8001.log 2>&1 &
```

- **必须在部署目录根下运行**：`loader.py` 的默认数据路径是 CWD 相对的
  （`data/full_station_database/…`、`outputs/hydrodynamics_preprocessed/…`）。
- 脚本自带 `sys.path.insert(src)`，无需手工设 `PYTHONPATH`。
- 该服务 `--reload` 未开；改 agent 源码后需手动重启进程生效。

## 4. DeepSeek（LLM 环节，可选）

AquaTurbGPT 规划 / 知识库问答默认走 DeepSeek（`os.getenv("DEEPSEEK_API_KEY")`）。
**不设 key 时服务可正常起**，但 LLM 环节降级为 mock/规则兜底；设了才达到合作方线上质量。

```bash
cd /Users/mac/Project/WaterExpert/agent
echo 'DEEPSEEK_API_KEY=sk-...' >> .env        # 该仓库 .env 已被 .gitignore 忽略
# 重启服务使 .env 生效（run 脚本是否自动载入 .env 以源码为准；否则 export 后重启）
```

平台侧无需感知 key——它只代理 agent API。

## 5. 验证

```bash
BASE=http://127.0.0.1:8001/api
curl -sS $BASE/health      # 期望 {"status":"healthy","agents":{…6 项全 ready}}
curl -sS $BASE/scenarios   # 期望 S1–S4 场景码表
curl -sS $BASE/status      # 含 data_loader（真实读取 2586 站点数据行数）
```

平台侧端到端：启动平台后端后访问任一 agent 页面（知识图谱 → QA），跑一个策略任务并
查看"诊断说明 + 相似案例"卡片（explain）。agent 不可达时平台日志会给出 URL 归属提示
（本地 :8001 未起 / 隧道轮换二选一）。

## 6. 合作方代码更新时

`agent/` 已并入本仓库（不再是合作方仓库的本地 clone，无独立 .git）。若合作方日后推送新版本：
diff 其新快照与 `agent/src`，把需要的改动合入 `agent/`（agent 的 `src/water_ai/{models,physics}`
本质源自我方研究仓，见第 8 节）；`data/`、`outputs/` 的差异仍以本地/线上实际运行内容为准。
平台只依赖 HTTP 契约（INTEGRATION_GUIDE.md），agent 内部实现变更不要求平台改动。

## 7. 已知边界

- **任务状态在内存**：重启即清空（无 Redis/Celery，`api_jobs/` 仅供审计留档）。
- **仅本机可达**：`127.0.0.1:8001` 绑定 loopback；若平台后端将来迁到另一台机器，
  需把 agent 一并迁走并把 `WATEREXPERT_AGENT_API_URL` 指到其新地址。
- 未做 systemd 常驻；机器重启后需按第 3 节手动拉起（可用 `start_water_api.sh` 思路包装）。

## 8. 模型核心统一（换芯，2026-09-08）

**背景**：合作方 agent 仓库是我们研究代码 `src/water_ai` 的衍生+精简版。逐项比对确认
**我们的 MSCIM/CMFBE 更新更强**（我方 mscim 有 boundary_head/risk_head/时序池化，cmfbe 为
自适应融合门控；参数量约大 20%），而合作方线上一直跑他们的旧精简模型。两版 checkpoint 键关系为
**合作方 ⊆ 我方**、56 个 feature_columns 名称顺序逐一同 → 换芯在结构上可行。

**已执行**（本地部署）：
```bash
cd /Users/mac/Project/WaterExpert/agent
# 备份合作方原版
mkdir -p .swap_backup_20260908/{models,weights}
cp src/water_ai/models/{mscim,cmfbe_stgcn}.py .swap_backup_20260908/models/
cp outputs/models/{mscim,cmfbe_stgcn,mscim_no_kg}.pt .swap_backup_20260908/weights/
# 换入我方核心（代码必须与权重一起换；agent 侧 strict=True，只换权重会因多余 key 报错）
cp ../src/water_ai/models/{mscim,cmfbe_stgcn}.py src/water_ai/models/
cp ../outputs/models/{mscim,cmfbe_stgcn,mscim_no_kg}.pt outputs/models/   # 已并入同仓库,直接同级取
# 重启并验证
.venv/bin/python scripts/run_api_server.py --host 127.0.0.1 --port 8001   # 或重启既有进程
```

**验证结果**：health 6 agent ready；4 场景 strategy 均 ~3s completed、无 strict/load 报错；
explain 案例命中不变。策略可见核心差异（如 s2/s3/s4 现产生曝气强度，此前旧模型几乎恒为 0）。

**影响与回滚**：换芯后本地 agent 行为 ≠ 合作方自己服务器的行为（两套核心并存）。若需与合作方
结果逐位对齐，可回滚 `.swap_backup_20260908/` 内的代码与权重后重启。长期建议把
`src/water_ai/models`（及 data/physics）定为我方唯一权威源，agent 侧直接消费，不再维护第二份拷贝。
