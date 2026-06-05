# xberif

`xberif` 是给芯片验证项目生成和查询 agent context summary cards 的工具。它把项目知识按 topic 拆成短 summary card 和可展开 detail markdown，让后续 debug agent 可以先读紧凑概要，需要时再按 topic 拉取细节。

它回答的问题很窄：

- 这个验证环境有哪些关键 topic？
- 某个 topic 的短 summary、关键项和 evidence 是什么？
- 需要展开时，对应 detail markdown 在哪里、内容是什么？
- 当前项目应该给 agent 注入哪一组 context？

它明确不做：

- 不读 RTL/FSDB 事实。
- 不做 bit 计算。
- 不解析 entry 或 descriptor。
- 不替代 `xdebug`、`xbit`、`xentry`、`xloc` 的确定性工具能力。

## Quick Start

```bash
make -C xberif test

# 在一个项目目录里初始化 BT 模板配置
<xverif-root>/tools/xberif config init --kind bt

# 真实生成 cards/details 时必须显式指定模型
<xverif-root>/tools/xberif init --model opus
```

### Shell 命令入口

为了在任意目录和 Claude Code 这类非交互 shell 中稳定调用，建议把仓库 `tools/` 加入 `PATH`。下面示例里的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换。

Bash / Zsh：

```bash
export XVERIF_HOME=<xverif-root>
export PATH="$XVERIF_HOME/tools:$PATH"
# 可选：未设置时 tools/xberif 会优先找 ~/miniconda3/envs/xberif-py311/bin/python。
export XBERIF_PYTHON="$HOME/miniconda3/envs/xberif-py311/bin/python"
```

Tcsh：

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv PATH "$XVERIF_HOME/tools:$PATH"
setenv XBERIF_PYTHON "$HOME/miniconda3/envs/xberif-py311/bin/python"
```

配置后可以直接使用：

```bash
xberif config init --kind bt
xberif init --model opus
xberif brief --mode debug
xberif get backpressure
xberif detail backpressure
```

`tools/xberif` 的 Python 选择顺序是：`XBERIF_PYTHON`、`~/miniconda3/envs/xberif-py311/bin/python`、`~/miniconda3/bin/python`、`python3`。

## 工作流

### 1. 初始化项目配置

```bash
xberif config init --kind bt
```

支持的 kind 来自内置模板，当前包括 `bt`、`it`、`st`、`soc`。命令会在当前项目生成 `xberif/` 配置目录、topic prompt 和 view 配置，不会生成 `.xberif/` 状态目录。

常用选项：

- `--kind <bt|it|st|soc>`：选择验证环境类型。
- `--force`：覆盖已有配置。
- `--merge`：合并已有配置。
- `--dry-run`：只打印将写入的文件。
- `--output <dir>`：指定输出项目根目录。

### 2. 运行 agent 生成 cards/details

```bash
xberif init --model opus
```

`--model` 是必填项。模型来源保持单一：命令行传入，运行时追加到 agent command；`kind.toml` 不保存默认 model，`agent.command` 里也不应重复写 `--model`。

运行后生成 `.xberif/` 状态目录，主要内容包括：

- `.xberif/cards.json`：topic card catalog。
- `.xberif/details/*.md`：每个 topic 的展开说明。
- `.xberif/manifest.json`：项目扫描和 topic manifest。
- `.xberif/kind.json`：当前 env kind 状态。
- `.xberif/raw/claude-xberif-guard-settings.json`：可手动合并到 `.claude/settings.json` 的 Claude hook 片段，用于阻止 Claude 直接读写 `.xberif`。

`xberif init` 不会创建或修改 `.claude/settings.json`。如果希望 Claude 普通任务不能直接 Read/Edit `.xberif`，请把 `.xberif/raw/claude-xberif-guard-settings.json` 里的 `hooks` 片段手动合并到项目 `.claude/settings.json`。

### 3. 查询 context

```bash
xberif list-topics
xberif status
xberif --json status
xberif brief --mode debug
xberif get backpressure
xberif get backpressure --detail
xberif detail backpressure
```

常用命令：

查询类命令默认输出 `xout` 结构化文本；需要完整 JSON 时把全局 `--json` 放在子命令前，例如 `xberif --json status`。`agent serve --stdio` 和 hook 协议仍保持 JSON。

- `list-topics`：列出当前项目已有 topic。
- `status`：区分 `not_configured`、`configured_only`、`generated_raw`、`ready`、`invalid`，用于诊断 cards/detail/catalog 是否一致。
- `brief --mode <mode>`：按 view 输出短 context。
- `get <topic>`：默认输出 topic card 的 xout 摘要。
- `get <topic> --detail`：直接输出 detail markdown。
- `detail <topic>`：输出 detail markdown。
- `repair-catalog`：当 `.xberif/cards/*.json` 和 details 已存在但 `.xberif/cards.json` 为空或不同步时，重新 reconcile/update/validate。

`.xberif/` 是 xberif 管理的状态目录。初始化完成后的 Claude 普通任务不应直接读取或编辑 `.xberif/cards.json`、`.xberif/cards/*.json` 或 `.xberif/details/*.md`；读取请使用 `xberif status/brief/list-topics/get/detail`，维护请使用 xberif card/detail 工作流、`repair-catalog` 和 `validate`。

### 4. Agent/RPC 入口

```bash
xberif agent serve --stdio
xberif agent serve --stdio --write
```

默认只读；加 `--write` 后允许 agent 通过 RPC 写入 card/detail。写路径仍会经过 schema 和 hook 校验。

## Card 和 Detail 合同

card 是短摘要，适合塞进 agent 初始上下文；detail 是展开说明，适合按需读取。

约束：

- `summary` 保持短而明确，概括 topic 结论。
- `key_items` 记录关键项、单句说明、confidence 和 evidence。
- `detail.available` 为 true 时，应存在 `.xberif/details/<card_id>.md`。
- detail markdown 使用 YAML frontmatter，并包含固定章节。
- detail 标题和 metadata 必须与 card 对齐。

写入入口：

```bash
cat card.json | xberif card upsert --stdin
cat detail.md | xberif detail upsert backpressure --stdin
xberif validate
```

## Claude Hook 片段

- `.xberif/raw/claude-settings.json` 只用于 `xberif init` 子进程的临时 validate hook。
- `.xberif/raw/claude-xberif-guard-settings.json` 是给用户手动合并的持久 guard 片段；xberif 不会自动改 `.claude/settings.json`。
- 如果 guard hook 阻止 Claude 访问 `.xberif`，改用 xberif skill 或 CLI 查询/维护数据，不要绕过 hook 直接读写状态文件。

## 构建与测试

```bash
make -C xberif
make -C xberif test
```

`xberif` 是 Python 3.11+ 工具，运行依赖 `typer`、`rich`、`pydantic`、`jsonschema`、`tomli-w`、`pathspec`，测试依赖 `pytest`。
