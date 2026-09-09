# WaterExpert 生产运行手册（Aliyun ECS 新加坡）

> 上线日期 2026-09-09。生产 = 新仓库 `SSSuperfriendly/WaterExpert-Platform`（`main`）
> 部署到一台阿里云 ECS：Ubuntu 22.04.5、2 vCPU、3.4 GiB RAM、49 GB，公网 `47.84.185.231`。
> 部署形态：**systemd + Python venv**（不用 Docker；仓库里的 Dockerfile/compose 保留备查）。
> 无域名阶段先走 **HTTP :80**；有域名后再平滑切 HTTPS。

## 拓扑

```
公网 :80  ─ nginx（client_max_body_size 700m）
              └ 127.0.0.1:8000  waterexpert-platform.service  (uvicorn, 1 进程, 静态 /ui + 全部 /api)
                    └ var/ = /srv/waterexpert/app/var   ← sqlite/上传/报告/KG，随目录持久
              └ 127.0.0.1:8001  waterexpert-agent.service  (run_api_server.py, 仅 loopback)
```

- 运行用户 `waterexpert`（sudo，NOPASSWD；密码登录已全局关闭，仅密钥）。
- 服务器不装 Node/不跑 git：代码与 `frontend/out` 由维护机 rsync 上去（`scripts/deploy/`）。
- **单机约束**：两服务各 1 进程（`--workers` 禁用，单调度器）；平台任务并发=1
  （`WATEREXPERT_MAX_CONCURRENT_JOBS=1`）；系统配 2 GiB swap 兜底峰值。

## 一、日常状态巡检

维护机执行：

```bash
./scripts/deploy/status.sh        # 单位状态 + 两级健康 + agent 健康 + 公网入口 + 磁盘/内存/swap
curl -s http://47.84.185.231/healthz    # liveness
curl -s http://47.84.185.231/readyz      # readiness（DB 可写 + 磁盘 ≥2GiB，不满则 503）
```

公网两条不通多半是阿里云安全组没放行 TCP 80；`readyz` 挂查磁盘/`var/state`。

## 二、上线（半自动发布）

一切经 `./scripts/deploy/release.sh`（维护机、要求 git 工作区干净）：

```bash
cd /Users/mac/Project/WaterExpert
git fetch platform && git checkout main && git pull platform main   # 先在本地对齐最新
./scripts/deploy/release.sh                          # 平台 + 前端 + agent 全量
./scripts/deploy/release.sh --scope=platform         # 只更平台
./scripts/deploy/release.sh --scope=agent            # 只更 agent
./scripts/deploy/release.sh --skip-checks            # 跳过本地 pytest/npm build（慎用）
./scripts/deploy/release.sh --tag=prod-YYYYMMDD      # 发布后打 tag 并推到 platform 远端
```

脚本行为：`pytest` + `npm run build` 自检 → rsync 仓库 tracked 路径（`backend configs scripts src
data outputs docs` + 根级文件）与 `frontend/out` → 重启受影响 systemd 服务 → 冒烟健康检查。
**rsync 只写列出路径，永不触碰服务器上的 `var/` 与 `.env`** → 状态安全。

发布前门禁 = 新仓库 CI（push/PR 自动跑 backend pytest + frontend build + e2e），红了不要发。

## 三、回滚

```bash
cd /Users/mac/Project/WaterExpert
git checkout <旧tag 或旧 sha>        # 例如 prod-20260909；git stash 会拦住未提交改动
./scripts/deploy/release.sh
# 用完后切回 main
```

同目录就地覆盖、`var/` 不动，回滚即重放旧版本。agent 回滚同理（`AGENT_LOCAL` 指向旧树再跑
`deploy_agent.sh`）。必要时先 `status.sh` + 当晚备份兜底。

## 四、备份与恢复

- 服务器 cron（root）：每晚打包 `/srv/waterexpert/app/var` → `/srv/backups/var-<date>.tgz`，
  保留 14 份；再把最近一份拉到维护机留异地副本。
- 恢复：停平台 → 解包覆盖 `/srv/waterexpert/app/var`（注意属主 waterexpert）→ 起平台。
- agent 无持久业务态（任务在内存；`outputs/api_jobs/` 仅审计），不备份。

## 五、账号

- 首启播种的生产账号即 **admin**（角色 admin），由 `/srv/waterexpert/app/.env`
  的 `WATEREXPERT_DEMO_USERNAME/PASSWORD/ROLE` 决定（root:root 600）。改密码 = 编辑该 .env 后
  `sudo systemctl restart waterexpert-platform`（seed 会 upsert）。
- 开放注册已关闭：`WATEREXPERT_ENABLE_REGISTRATION=0`，注册接口返回 403。
- 加人：临时设 `=1` 重启注册后再关，或直接改 `var/state/auth.sqlite3` 的 users 表（角色列）。

## 六、日志

```bash
ssh waterexpert@47.84.185.231
sudo journalctl -u waterexpert-platform -e --since "10 min ago"
sudo journalctl -u waterexpert-agent   -e
tail -f /var/log/nginx/waterexpert.access.log   # 若启用了 json/combined
```

平台/agent 子进程任务日志在各任务目录 `var/state/job_runs/<id>/logs/`（页面可下载）。

## 七、升级维护注意事项

- 依赖变化才需重建 venv（平台 `pip install -r requirements.txt`，agent 用精简清单
  `scripts/deploy/agent-requirements-linux.txt`）。安装很慢且吃内存 → 在 swap 下做、放后台盯。
- requirements/大改动先在维护机全量自检；发布失败可随时回滚（第三节）。
- 容量告警：`/readyz` 磁盘 <2GiB 即 503；大上传/报告多了用维护接口清理或手动清
  `var/state/job_runs`（30 天默认保留，`POST /api/v1/admin/maintenance/cleanup`）。

## 八、安全

- SSH：仅密钥；root 与 `waterexpert` 均禁密码登录（`99-codex-stability.conf`）。
- 阿里云安全组当前放行 22/80（80 建议先只放维护机 IP）。443 未开（无域名）。
- 上线 HTTPS（有域名后）：A 记录指向本机 → certbot（nginx 插件）签证书 → nginx 加 443
  server 块并把 80 跳 443；CORS 里补 `https://<域名>`。无需改应用。
- 生产 .env 含 JWT secret / 运营账号密码：**勿提交、勿外传**；换 key 即改 .env + 重启。

## 九、开发 / 检测 / 上线 / 维护 节奏

| 阶段 | 动作 | 门禁/产出 |
|---|---|---|
| 开发 | `feature/*` 分支本地双服务联调（`scripts/dev/start_local.sh` + agent :8001） | 手动冒烟 |
| 检测 | push/PR 到新仓库 `platform` | CI：backend pytest + frontend build + e2e 全绿 |
| 上线 | 合入 `main`（绿）→ 打 tag → `release.sh --tag=prod-*` | status.sh 全绿 |
| 维护 | `status.sh` 巡检、journalctl、cron 备份、旧 tag 回滚 | — |
