# Water AI 本地完整部署 —— 请贵方补齐以下文件（转发给部署方）

> **状态更新（2026-09-08）**：本文档所列缺失文件已通过合作方提供的三份 zip 补齐并
> **完成本地完整部署**（见 [AGENT_LOCAL_RUN.md](AGENT_LOCAL_RUN.md)）。本文档留档——
> 若部署目录需在别处重建，仍可按第二、三节向合作方索取这些文件。

> 背景：我方已将贵方 GitHub 仓库 `vvvlun/agent-water-expert` 克隆到本地，准备
> **在自己服务器完整部署这套 Water AI API**（替代不稳定的临时隧道），以便长期稳定联调。
> 但克隆后发现：**贵方发布到 GitHub 的目录 ≠ 服务器上实际运行的那份**——
> 启动 API 必需的 `src/water_ai/data/` 包（`WaterQualityDataLoader`）在仓库里不存在，
> `data/`（相似案例库等）也不在，服务当前无法启动。
> 请贵方按下列方式把**实际运行目录**里的缺失内容补齐给我方即可，无需重新整理文档。

---

## 一、最省事的做法（推荐，任选其一）

贵方服务实际运行在 `/home/xchen2/WaterExpert-main`。请二选一：

- **方式 A：直接把整个运行目录打包发我**
  ```bash
  cd /home/xchen2/WaterExpert-main
  tar --exclude='.git' --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
      --exclude='.env' -czf water-main.tar.gz .
  ls -lh water-main.tar.gz
  ```
  把 `water-main.tar.gz` 通过网盘/文件传输发给我方即可（若太大，见方式 B）。

- **方式 B：只补 GitHub 上缺失/有差异的部分**

  1. 若该目录是 git 仓库，先告诉我当前版本并直接补齐推送：
     ```bash
     cd /home/xchen2/WaterExpert-main
     git rev-parse HEAD; git status --short
     ```
     然后把本地新增/修改（尤其 `src/water_ai/data/`、`data/`）提交推送到
     GitHub，我方重新 pull。
  2. 若不是 git 仓库，请打包这几处发我：
     ```bash
     cd /home/xchen2/WaterExpert-main
     tar -czf water-missing.tar.gz \
         src/water_ai/data \
         data \
         outputs/models \
         outputs/intermediate \
         configs \
         scripts/run_api_server.py
     ```
     （若 `outputs/` 较大，`outputs/models` 与 `outputs/intermediate` 至少发我。）

> 请务必以**服务器实际运行目录**为准，而不是重新整理一份"干净版"——GitHub 快照
> 与我们验证过的线上行为存在差异，缺一个文件就可能导致行为不一致。

---

## 二、需要确认的几件事（逐条回复即可）

1. **代码版本**：服务器上这份代码与 GitHub `2026-09-02` 快照差异大吗？
   运行目录是否为 git 仓库？若是，HEAD 是哪个 commit？（便于对齐。）
2. **模型权重**：我方本地已有 `outputs/models/mscim.pt`、`cmfbe_stgcn.pt`
   （同为 WaterExpert 训练产物，结构 `state_dict` + `meta.feature_columns` 一致）。
   请确认服务器上这两份是否就是同一批权重。稳妥起见，请运行下面命令把 md5 发我核对：
   ```bash
   md5sum outputs/models/mscim.pt outputs/models/cmfbe_stgcn.pt
   ```
3. **DeepSeek**：LLM 环节（AquaTurbGPT 规划 / 知识库问答）调用的是标准
   `api.deepseek.com` 吗？我方会自备 `DEEPSEEK_API_KEY`，只需确认**接口地址与模型名**
   （默认 `https://api.deepseek.com` + 官方模型即可，若贵方用了自定义 base_url 或网关
   请告知）。
4. **启动方式**：确认运行命令与我方读到的一致——
   ```bash
   cd <运行目录> && PYTHONPATH=src python scripts/run_api_server.py --host 0.0.0.0 --port 8000
   ```
   另外服务是否用 `systemd`/tmux 常驻（`water-ai-api.service`）？重启后任务状态是否清空
   （我了解到是内存态，重启即失效，确认即可）。

---

## 三、我方拿齐后的本地运行方式（供了解，无需贵方操作）

- 平台服务地址将从临时隧道切到本地：`http://127.0.0.1:8001/api`（我方独立端口，避免冲突）。
- 我方复用本地已有的同款权重与数据集，不做任何训练，仅部署推理 API。
- 接入的 5 个接口不变：health / scenarios / strategy / strategy/{id} / explain。
