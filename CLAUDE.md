# tg-course-worker

多频道 Telegram 内容生产 + 分发流水线。素材（URL / txt / md / 转发消息）经 LLM
路由分类、生成文案、人工审核后进入某个频道的待发队列，按各频道自己的排期发布。
带一个服务端渲染的管理后台。

当前进度、没做完的事、以及待拍板的决定，见 [HANDOFF.md](HANDOFF.md)。

## 运行环境（重要）

**本项目一律在 conda 虚拟环境 `tg-course-worker` 中运行，Python 3.12。**

任何执行 Python 的命令都必须先激活环境，不要用系统 Python、不要用 `python3`
直接跑、不要新建 venv：

```bash
conda activate tg-course-worker
```

一次性命令可以用 `conda run` 避免忘记激活：

```bash
conda run -n tg-course-worker python -m app.main
```

本机的环境在 `E:\run\conda_envs\tg-course-worker`（`.condarc` 把 envs_dirs
指到了 E 盘，不在默认的 `~/miniconda3/envs` 下）。

目标部署平台是 Ubuntu 22.04 / 24.04 / 26.04。代码不得依赖 Windows 特性：
路径统一用 `pathlib`，不要硬编码 `\` 或盘符，不要调用 `os.startfile`、
`win32api` 之类。

**所有文件一律 LF 换行**，`.gitattributes` 已经强制。在 Windows 上改文件时注意：
Python 的 `open(p, "w")` 默认会把换行翻译成 CRLF，写文件要带上
`newline="\n"`，或者直接用二进制模式。带 CRLF 的 shell 脚本在 Linux 上会报
`/usr/bin/env: 'bash\r': No such file or directory`——内核真的在找一个叫
`bash\r` 的程序，报错完全不指向换行符本身。

## 常用命令

```bash
conda run -n tg-course-worker python scripts/bootstrap.py     # 首次引导：建第一套 bot/方向/频道
conda run -n tg-course-worker python -m app.main              # 启动全部服务
conda run -n tg-course-worker python -m app.tools.dryrun --render-only   # 不连 TG 验证渲染
conda run -n tg-course-worker python -m app.tools.dryrun x.md --level P1 # 跑真实流水线
```

服务器上（Ubuntu，systemd）：

```bash
sudo deploy/install.sh          # 安装 / 升级，幂等
tg-course-worker-restart        # 重启
journalctl -u tg-course-worker -f
```

## 架构

```
生产 Bot（私聊，仅 OWNER_ID）        后台 /ingest（链接 / 文本 / 文件）
  ingest → classify(路由到方向) → generate → 审核卡片 ⇄ 修订 → 选频道入队
                                                              │
管理后台 (FastAPI, 127.0.0.1:8080) ──── 同一进程，共用 db 和 pipeline
                                                              │ 每频道独立 cron
                                                              ▼
                                        频道（publisher bot 作为管理员发布）
                                          + [获取完整资料] 深链按钮
                                                              │
                                                   售卖 Bot（/start item_N_cM）
```

- `app/db.py` 存储层。配置层 `bots` / `verticals` / `channels`，内容层
  `items` / `drafts` / `queue` / `published`
- `app/botpool.py` Bot 实例池，按 `token_env_key` 从环境变量取 token
- `app/ingest/` 素材摄入，按输入类型分发
- `app/llm/` LLM provider 抽象 + 流水线（路由分类 / 生成 / 修订）
- `app/bots/producer.py` 生产 bot；`app/bots/sale.py` 售卖 bot
- `app/publisher.py` 频道发布；`app/scheduler.py` 每频道一个 job + 热重载
- `app/health.py` 频道健康检查（bot 还在不在、有没有发布权限）
- `app/web/` 管理后台：`routes.py` 内容侧、`routes_ingest.py` 录入、`routes_admin.py` 配置侧
- `app/intake.py` 后台摄入队列。Web 录入不在请求里跑流水线（两次 LLM 调用要二三十秒），建完条目就返回，剩下的扔进这里
- `config/prompts/` prompt 模板，**核心资产**，改这里不用改代码

## 约定

- 配置全部走 `config/settings.py`（pydantic-settings 读 `.env`），
  不要在代码里散落 `os.getenv`。例外：`botpool` 要按库里存的变量名取任意
  环境变量，所以 `settings.py` 额外调了一次 `load_dotenv()`
- **bot token 永不入库**，库里只存 `token_env_key`。数据库要备份、要挂卷、
  后台页面可能误显示，明文 token 泄露等于 bot 被接管
- **素材原文 (`items.raw_text`) 永不删除**：prompt 迭代后要重跑历史素材
- Telegram HTML 只支持 `<b> <i> <u> <s> <code> <pre> <a> <blockquote> <tg-spoiler>`，
  **没有** `<h1>` `<ul>` `<li>` `<p>` `<br>`。正文上限 4096，带图 caption 只有 1024。
  所有出站文案必须先过 `app/render.py:sanitize()`
- 发布身份必须是 bot 不能是 userbot：userbot 发的消息带不了 inline 按钮
- 审核状态落库，不放内存：进程重启不能丢
- `callback_data` 上限 64 字节，只放 id，内容从库里取
- 频道配置改动后要调 `scheduler.reload()` 热重载 cron job，不要求重启进程
- 后台是服务端渲染（Jinja2 + 原生表单 + POST-Redirect-GET），
  **不引入前端构建步骤**。少量交互用原生 fetch，不上框架

## 安全

- `.env`、`data/`、`*.session` 已在 `.gitignore` 中，任何情况下不要提交
- 生产 bot 的所有 handler 必须校验 `OWNER_ID`
- 后台默认绑 `127.0.0.1`，用 SSH 隧道访问；不要为了图方便改成 `0.0.0.0`
  暴露到公网（没有 HTTPS，密码会明文过网）。真要对外开，
  用 `deploy/nginx/` 那套反代 + HTTPS，`WEB_HOST` 仍然保持 `127.0.0.1`
- `WEB_PASSWORD` 为空时后台不启动，这是刻意的——不给无密码入口留口子
