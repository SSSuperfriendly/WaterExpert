# Water AI Agent —— 本地部署运行手册

> 合作方的 Water AI Multi-Agent 推理 API（此前经 Cloudflare 临时隧道接入，会随
> `cloudflared` 重启而失效）现已**完整部署到本机**，平台默认直连本地 `127.0.0.1:8001`，
> 不再依赖外部隧道。本文档说明部署目录、启动/重启、验证与升级方式。

---

## 1. 状态与拓扑

| 项 | 值 |
| --- | --- |
| 部署目录 | `/Users/mac/Project/agent-water-expert`（合作方 GitHub 快照 clone + 其实际运行文件覆盖） |
| 运行端口 | `127.0.0.1:8001`（避开平台后端 `:8000`；平台与 agent 同机共存） |
| Python | py3.12 venv：`.venv/`（uv 创建，API 运行时依赖已装） |
| 平台默认指向 | `WATEREXPERT_AGENT_API_URL` 未设时 → `http://127.0.0.1:8001/api` |
| 已接入接口 | `health / status / scenarios / strategy / strategy/{job_id} / explain / stage / jobs` |
| 2026-09-08 验证 | 6 agent 全 ready；4 场景 strategy 均 completed（~3s/个）；explain 命中案例库 |

平台后端（FastAPI :8000）只做 httpx 反向代理（`backend/app/services/external_agent.py`），
浏览器永不直接访问 agent；agent 宕机 → 平台返回 502 `agent_unavailable`，前端本地化提示。

## 2. 目录是如何组装的（复现/审计用）

部署树 = **GitHub 快照 `git@github.com:vvvlun/agent-water-expert.git`**（2026-09-02，
含 src/water_ai、configs、scripts、docs 等）+ 覆盖合作方**实际运行目录**的三份 zip
（原文件在 `/Users/mac/Project/WaterExpert/`，与源码快照的差异正对应此前启动缺失项）：

| zip | 顶层 | 落到部署目录的何处 | 提供内容 |
| --- | --- | --- | --- |
| `src_data.zip` | `data/*.py` | `src/water_ai/data/` | `loader.py` 等数据加载源码包（此前缺失 → 启动崩溃根因） |
| `案例库_data.zip` | `data/{case_library,…}` | `data/` | 相似案例库、全站点数据库、知识图谱、tech 知识库、raw |
| `outputs.zip` | `outputs/` | `outputs/` | **合作方真实权重**与中间产物（models/intermediate/diagnosis/…） |

真实权重 md5（溯源 / 对比用）：

```
outputs/models/mscim.pt        = 442ee7a491e12526de94e97a35af43a2
outputs/models/cmfbe_stgcn.pt  = 6e553a9386e4b8e857770f112ca76d7f
outputs/models/mscim_no_kg.pt  = a3ce7ac02b9d672e4b4640e7e5c56b7a
```

> 若部署目录需在另一台机器重建：clone 上述 GitHub 仓库 → 同法解压三份 zip 到对应位置 →
> 建 venv 装 `requirements-api.txt` 即可（`tigramite`/`vllm` 仅训练侧需要，API 启动不依赖）。

## 3. 启动 / 重启

```bash
cd /Users/mac/Project/agent-water-expert

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
cd /Users/mac/Project/agent-water-expert
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

本地部署不是 fork：若合作方推送了新代码，重新 pull 后对照上面第 2 节确认 `data/`、
`outputs/` 是否仍由 zip/线上提供，重启验证即可。平台只依赖 HTTP 契约
（INTEGRATION_GUIDE.md），agent 内部实现变更不要求平台改动。

## 7. 已知边界

- **任务状态在内存**：重启即清空（无 Redis/Celery，`api_jobs/` 仅供审计留档）。
- **仅本机可达**：`127.0.0.1:8001` 绑定 loopback；若平台后端将来迁到另一台机器，
  需把 agent 一并迁走并把 `WATEREXPERT_AGENT_API_URL` 指到其新地址。
- 未做 systemd 常驻；机器重启后需按第 3 节手动拉起（可用 `start_water_api.sh` 思路包装）。
