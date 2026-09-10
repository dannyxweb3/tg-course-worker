# tg-course-worker

多频道 Telegram 教程内容流水线，带管理后台。

素材（链接 / txt / md / pdf / 转发消息）丢给生产 Bot → LLM 判定它属于哪个内容方向、
生成文案 → 你在私聊或后台审核改稿 → 通过后进某个频道的待发队列 →
按各频道自己的排期发布，消息底部自动挂购买 Bot 的深链按钮。

## 快速开始

```bash
conda create -n tg-course-worker python=3.12 -y
conda activate tg-course-worker
pip install -r requirements.txt
```

填好 `.env`（见下），然后：

```bash
python scripts/bootstrap.py   # 建第一套 bot / 内容方向 / 频道
python -m app.main            # 启动
```

打开 <http://127.0.0.1:8080>，用 `.env` 里的 `WEB_PASSWORD` 登录。

不连 Telegram 先本地验证渲染：

```bash
python -m app.tools.dryrun --render-only
```

## .env 怎么填

| 变量 | 怎么拿 |
|---|---|
| `OWNER_ID` | 给 @userinfobot 发条消息，它回你的数字 id |
| `PRODUCER_BOT_TOKEN` | @BotFather `/newbot`，这个 bot 只你自己用 |
| `SALE_BOT_TOKEN` | 再建一个，面向读者，同时作为第一个频道的发布身份 |
| `CHANNEL_ID` | 把发布 bot 设为频道管理员后，在频道发条消息转发给 @userinfobot，形如 `-100xxxx` |
| `DEEPSEEK_API_KEY` | platform.deepseek.com |
| `WEB_PASSWORD` | 自己定。**留空则后台不启动** |
| `WEB_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |

**token 只存在 `.env`，不进数据库。** 库里存的是变量名。加第三个 bot 的顺序是：
先在 `.env` 加一行 `BOT_EN=123:AAA...` → 重启进程 → 后台「Bot」页用变量名
`BOT_EN` 建记录。

**发布身份必须是 bot**，且要在频道里勾选「发布消息」权限。这是硬要求：
userbot 发的消息带不了 inline 按钮，而「底部挂购买 bot」就是 inline 按钮。

## 管理后台

| 页面 | 干什么 |
|---|---|
| **总览** | 频道卡片：健康状态、绑定的 bot、排期、队列长度、下一条要发什么 |
| **待发队列** | 按频道分组，▲▼ 调顺序、指定发布日期、立即发布、移出 |
| **素材库** | 状态/方向筛选 + 关键词搜索 + 分页 |
| **素材详情** | 左边改稿右边实时预览（所见即所发）、版本切换、让 AI 按意见重写、换档位重跑、加入某个频道的队列 |
| **频道 / 内容方向 / Bot** | 增删改，改完排期热重载，不用重启 |
| **关系图** | Bot → 频道 → 方向 的连线图，自动列出断点（bot 缺 token、方向没频道承接、频道没绑发布 bot） |

后台默认只绑 `127.0.0.1`。远程访问用 SSH 隧道，不需要域名和证书：

```bash
ssh -L 8080:127.0.0.1:8080 user@your-server
```

## 多频道模型

三层拆开，因为它们不是 1:1 的关系——一个 bot 可以管多个频道，
一个方向可以同时有中文号和英文号：

```
bots ──┬──(publisher)──▶ channels ──▶ verticals（内容方向）
       └──(sale)────────▶     │
                              ▼
                          queue（按频道分，一稿可多投）
```

- **bots** 名称 / 角色 / `token_env_key`（不是 token 本身）
- **verticals** 内容方向。`description` 喂给分类器决定素材归属，
  `style_prompt` 可覆盖全局调性
- **channels** chat_id + 发布 bot + 售卖 bot + 方向 + **自己的 cron 和时区**

素材进来时，分类器一次调用给所有方向打分并选出归属（成本和单方向时几乎一样），
你在卡片或后台随时可以改。

## 使用

在生产 Bot 私聊里直接丢素材，支持：

- 一段文字
- 一个链接（自动抓正文；GitHub 仓库页会自动换成 raw README）
- `.md` / `.txt` / `.pdf` 文件
- 从别的群或频道转发的消息（自动保留出处，用于归属声明）
- 相册 / 多文件（自动聚合成一条，不会刷出多张卡片）

命令：`/queue` 各频道队列，`/channels` 频道和绑定关系，`/status` 状态计数，
`/cancel` 退出输入态。

## 处理档位

| 档位 | 做什么 | 典型场景 |
|---|---|---|
| P0 原样清理 | 只删推广尾巴、@、邀请链接，不动措辞 | 别人频道的现成教程，几乎原样转 |
| P1 轻排版 | 加标题、分段、代码块、TL;DR、踩坑提醒 | 内容好但结构松散 |
| P2 重写 | 提炼要点，用频道口吻重写，可合并多份素材 | 一份 txt 教程整理成帖 |
| P3 丢弃 | 哪个方向都不沾边 | 自动判定，可强制覆盖 |

## 部署到 Ubuntu

```bash
git clone <repo> && cd tg-course-worker
cp .env.example .env && vim .env
docker compose up -d
docker compose exec worker python scripts/bootstrap.py
docker compose logs -f
```

用 long polling 而不是 webhook，所以**不需要域名、证书、公网入口和反向代理**。
后台端口只映射到宿主机 `127.0.0.1`，走 SSH 隧道访问。

`data/`、`logs/`、`config/prompts/` 都挂了卷：数据不随镜像重建丢失，
改 prompt 调整文案风格也不用重新 build。

备份（cron 每天一次）：

```bash
bash scripts/backup.sh
```

## 目录

```
app/
  main.py          入口：生产 bot + N 个售卖 bot + 调度器 + 后台，一个进程
  db.py            SQLite 存储层
  botpool.py       Bot 实例池，token 从环境变量取
  render.py        Telegram HTML 清洗 + 分片（LLM 越界的标签在这兜住）
  publisher.py     频道发布
  scheduler.py     每频道一个 cron job + 热重载 + 低水位提醒
  health.py        频道健康检查
  ingest/          素材摄入：url / document / forward / 相册聚合
  llm/             provider 抽象 + 流水线（路由分类 / 生成 / 修订）
  bots/            producer.py 生产端、sale.py 售卖端
  web/             管理后台（FastAPI + Jinja2，无前端构建步骤）
  tools/dryrun.py  不连 TG 的本地验证
config/prompts/    prompt 模板，核心资产
```

## 已知边界

- 纯 JS 渲染的页面抓不到正文，需要 Playwright 兜底
- 扫描版 PDF 没有 OCR
- 售卖 Bot 只落库和欢迎，**支付未接**（建议起步用 Telegram Stars，
  纯 Bot API 闭环，不需要外部支付商）
- 长文超 4096 字符按段落自动拆条，Telegraph 方案未做
- 去重只做 URL 归一化精确匹配，内容指纹未做
- 源频道自动监听需要 userbot，未做
- 后台是单用户 + 签名 cookie，没有 CSRF token（前提是只绑本机）
