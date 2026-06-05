# Codex 与 gstack 使用说明

本文件回答两个问题：

1. 这台机器上的 gstack / Codex 技能是否已经适配好？
2. 在这个项目里应该怎么用？

## 1. 当前检查结果

我已经确认：

- `gstack` 命令存在
  - 路径：`C:\msys64\mingw64\bin\gstack`
- Codex 技能目录存在
  - 路径：`C:\Users\dell\.codex\skills`
- 该目录下已安装大量 gstack 相关技能，例如：
  - `gstack-review`
  - `gstack-cso`
  - `gstack-office-hours`
  - `gstack-plan-eng-review`
  - `gstack-document-generate`
  - `gstack-qa`
  - `gstack-ship`

这说明本机已经把 gstack 技能链接进 Codex 技能目录，Codex 可以读取这些 `SKILL.md` 指令文件。

## 2. 要区分两件事

### 2.1 `gstack` 命令

这是终端里的 CLI / 浏览器工具能力，偏运行时工具。

### 2.2 Codex 技能

这是给助手读的“任务工作流说明”。它们位于 `~/.codex/skills/` 下，通常不是让你手敲 shell 命令完成全部工作，而是让助手在对话里按技能流程执行。

换句话说：

- `gstack` 命令偏工具层
- `/review`、`/cso`、`/office-hours` 这些偏助手工作流层

## 3. 在 Codex 里怎么触发技能

最直接的方式是在对话里明确写：

- `/review`
- `/cso`
- `/office-hours`
- `/plan-eng-review`
- `/qa`
- `/ship`

也可以用自然语言明确指定，例如：

- “请用 `/review` 检查当前改动”
- “请用 `/plan-eng-review` 审一下这个软件架构”
- “请用 `/cso` 看一下有没有敏感信息和安全问题”

## 4. 为什么你看到磁盘目录是 `gstack-review`，但对话里常写 `/review`

因为技能文件 frontmatter 里的名字是短名。例如 `gstack-review/SKILL.md` 的 frontmatter 名字是 `review`。因此对话里的调用名通常是短名：

- 磁盘目录：`gstack-review`
- 对话调用：`/review`

同理：

- `gstack-cso` 对应 `/cso`
- `gstack-office-hours` 对应 `/office-hours`
- `gstack-plan-eng-review` 对应 `/plan-eng-review`

## 5. 这个项目里最推荐的技能用法

### 5.1 需求与 MVP 拆解

用：

- `/office-hours`

适合：

- 明确软件做什么
- 哪些页面先做
- 先交付哪一条链路

### 5.2 架构与接口审查

用：

- `/plan-eng-review`

适合：

- 审查前后端分层
- 审查 API 设计
- 审查模型服务封装方式

### 5.3 代码改完后的审查

用：

- `/review`

适合：

- 提交前查逻辑问题
- 查结构性风险
- 查遗漏测试和文档

### 5.4 安全检查

用：

- `/cso`

适合：

- 检查敏感路径
- 检查凭据泄漏
- 检查部署与依赖风险

### 5.5 页面联调与体验检查

用：

- `/qa`

适合：

- 前端页面已有基础后
- 验证流程能不能走通
- 看报错、截图和交互行为

### 5.6 推送与交付

用：

- `/ship`

适合：

- 已经有 git 仓库
- 已有远程
- 需要提交、推送、PR

## 6. 针对这个项目的推荐工作流

建议下一位助手按这个顺序工作：

1. 先读 `README.md` 和 `AGENTS.md`
2. 用 `/office-hours` 或直接阅读 `docs/next_assistant_execution_plan.md` 明确第一阶段目标
3. 先搭后端桥接层和接口
4. 用 `/plan-eng-review` 看架构是否跑偏
5. 开始实现
6. 每轮主要改动后用 `/review`
7. 有 Web 页面后再用 `/qa`
8. 要提交时再用 `/ship`

## 7. 适用提醒

- `/review` 最适合在 git diff 已形成时使用。
- `/ship` 最适合在独立软件仓库已经初始化后使用。
- `/qa` 需要页面或接口已经能启动。
- `/cso` 很适合在准备对外共享仓库或部署前运行一次。

## 8. 对下一位助手的结论

可以认为当前机器上的 gstack 已经成功适配到 Codex 环境。你不需要重新安装技能，应该直接把这些技能当作项目工作流工具来用。
