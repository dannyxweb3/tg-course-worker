# 会话交接：从 Windows 开发机迁到 Linux

> 快照时间：2026-09-12。写给**在 Linux 开发机上新开的会话**看。
> 通用规则在 [CLAUDE.md](CLAUDE.md)，部署细节在 [deploy/README.md](deploy/README.md)，
> 这份只记**当前状态、没做完的事、和需要人拍板的决定**。

## 0. 新会话开场怎么说

把这句话丢给新会话就够了：

> 读一下 HANDOFF.md 和 CLAUDE.md，我们接着调试。

---

## 1. 迁移到 Linux

两条路，**开发机选 A**：

- **A. 直接从 clone 跑** —— 调试用。代码改完 `Ctrl-C` 重启就行，不用管 systemd
- **B. 装成 systemd 服务** —— 上生产用，见 [deploy/README.md](deploy/README.md)

两条路的 `.env` 和 `data/` 放的位置**不一样**，别搞混：
A 放在 clone 目录下，B 放在 `/opt/tg-course-worker/` 下。

### 1.1 先停掉 Windows 上的服务

**这一步不能跳。** 同一个 bot token 在两台机器上同时 long polling，
Telegram 会对其中一边返回 `409 Conflict`，两边都收不稳消息，
而且症状是间歇性的，很容易误判成代码有问题。

Windows 上结束 `python -m app.main` 那个进程即可。
（写这份文档时它还在跑：今早 08:00 的健康检查和 09:00 的定时发布都执行了。）

### 1.2 在 Windows 上导出数据

**不要直接 `cp worker.db`**——库是 WAL 模式，`.db` 之外还有 `-wal` 和 `-shm`，
只拷主文件会丢掉最近的事务。用 SQLite 的在线备份：

```bash
# 服务停掉之后再跑
python -c "import sqlite3;s=sqlite3.connect('data/worker.db');d=sqlite3.connect('data/worker-migrate.db');s.backup(d);d.close();s.close();print('ok')"
```

（有 `sqlite3` 命令行的话 `sqlite3 data/worker.db ".backup 'data/worker-migrate.db'"` 等价。）

要搬的东西：

| 搬什么 | 大小 | 不搬的后果 |
|---|---|---|
| `.env` | — | 服务起不来。里面有 1 个 DeepSeek key 和 3 个 bot token |
| `data/worker-migrate.db` → 落地改名 `worker.db` | 3 MB | 98 条待审核素材全没，重跑要 18 分钟 + 十几块 API 费 |
| `data/pdf/` | 8.3 MB，100 份 | 配套资料全丢，且库里的 asset 记录会指向不存在的文件 |
| `data/telegraph.json` | 116 B | Telegraph 账号 token，丢了之前发的全文页就改不了了 |

`data/media/` 是空的，不用管。`logs/` 不用搬。

`.env` 和 `data/` 都在 `.gitignore` 里，**不会随 git pull 过去**，只能手工搬。
用 `scp` 或 U 盘，**不要贴到聊天窗口里**。

### 1.3 路线 A：开发机直接跑

```bash
git clone <repo> && cd tg-course-worker

# Ubuntu 24.04+ 自带 3.12；22.04 需要先加 deadsnakes，见 deploy/README.md 的 3.x
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 把上一步搬来的东西放进项目根目录
#   ./.env
#   ./data/worker.db  ./data/pdf/  ./data/telegraph.json
chmod 600 .env

.venv/bin/python -m app.main
```

**不需要跑 `bootstrap.py`** —— 库里已经有 bot / 方向 / 频道记录了，
bootstrap 是给空库用的，重复跑虽然安全但没意义。

### 1.4 路线 B：装成服务

注意顺序：`install.sh` 只同步**代码**到 `/opt/tg-course-worker`，
`.env` 和 `data/` 它不会从 clone 目录搬过去，得装完再放。

```bash
git clone <repo> && cd tg-course-worker
sudo deploy/install.sh                    # 建目录、建账号、装 venv、装 unit，不启动

# 装完再把数据放到 /opt 下（不是 clone 目录）
sudo cp /path/to/.env            /opt/tg-course-worker/.env
sudo cp /path/to/worker.db       /opt/tg-course-worker/data/worker.db
sudo cp -r /path/to/pdf          /opt/tg-course-worker/data/pdf
sudo cp /path/to/telegraph.json  /opt/tg-course-worker/data/telegraph.json

sudo chown -R tgworker:tgworker /opt/tg-course-worker/data
sudo chown tgworker:tgworker /opt/tg-course-worker/.env
sudo chmod 600 /opt/tg-course-worker/.env

sudo systemctl start tg-course-worker
```

### 1.5 验一遍

```bash
curl -s localhost:8080/healthz          # 应当返回 ok
```

路线 A 看终端输出，路线 B 看 `journalctl -u tg-course-worker -f`。
应当能看到 3 个 bot 起来、scheduler 注册了频道的 cron job。

然后：

1. 给生产 bot `@aitoolstackdeskbot` 私聊发一条链接，看能不能出审核卡片
2. 打开后台（路线 A 直接 `http://127.0.0.1:8080`；路线 B 要 SSH 隧道），
   确认素材库里有 98 条待审核、100 份 PDF 资料还在

## 2. 当前状态快照

### 数据

| 项 | 数量 |
|---|---|
| 待审核 `review` | 98 |
| 已发布 `published` | 4 |
| 已分类未生成 `classified` | 1 |
| 失败 `failed` | 2 |
| 队列 `queue` | 0（空） |
| PDF 资料 `assets.kind=vault` | 99，**全部 `vault_msg_id=0`（待上传）** |
| Telegraph 全文页 | 1 |

内容方向分布：AI 工具与自动化 95、黑产手法与风控剖析 9、**副业与变现 1**。

### 配置

- 3 个 bot：生产机 `@aitoolstackdeskbot`、资料机 `@aitoolstackbot`、
  发布机 `@aitoolstackpostbot`
- 1 个频道 `AIToolStack`，每天 09:00 发一条，已启用
- 3 个内容方向：`ai-stack` / `side-income` / `risk-teardown`，
  三个的 `style_prompt` **都是空的**（所以文案风格目前只受全局 `system_style.md` 影响）

### git

- 分支 `main`，最新提交 `1399d08`
- **两个提交都还没 push**（`6f8afd2` 和 `1399d08`）
- `start.sh` 未提交，硬编码了 Windows 上的 miniconda 路径，Linux 上用不着

---

## 3. 没做完的事

### 3.1 仓库频道没配 —— 99 份 PDF 发不出去（优先级最高）

`.env` 里 `VAULT_CHANNEL_ID=0`。PDF 都在 `data/pdf/` 躺着，库里
`assets.vault_msg_id=0` 标记为"待上传"。

发布逻辑会**跳过**这些资料，所以现在发帖子不会挂「获取完整资料」按钮
（`publisher._cta()` 里判 `asset_count`）——不会发出半截东西，但资料也送不到读者手上。

要打通还差两件事：

1. 建一个私有频道，把生产 bot 和资料机都设为管理员，
   拿到 chat_id 填进 `VAULT_CHANNEL_ID`
2. **写一个后台批量上传的入口**——设计过了，代码没写。
   逻辑是：遍历 `assets where kind='vault' and vault_msg_id=0`，
   用生产 bot 把文件发进仓库频道，把返回的 `message_id` 回写进 `vault_msg_id`。
   `app/vault.py` 里的 `store()` 已经是单条版本，套个循环加个后台任务即可。

### 3.2 两条失败素材

`#31`（danilchenko.dev FastMCP）和 `#35`（charigent.com SEO 流水线），
失败原因都是 DeepSeek 返回的 JSON 被截断。素材原文还在库里，
在后台详情页点「重新生成」就能补。

### 3.3 会话 cookie 没有 Secure 标记

`app/web/auth.py` 里 `secure=False` 是硬编码的，为 SSH 隧道（明文 HTTP）场景写的。
挂 nginx 走 HTTPS 之后这仍是个缺口。详见 deploy/README.md 的 3.6 节。

想改就做成配置项（比如 `WEB_SECURE_COOKIE`，默认 false）。
**改完就不能再用隧道访问了**——置了 Secure 之后 `http://127.0.0.1:8080` 登不上去。

### 3.4 一个孤儿文件

`data/pdf/2-n8n_自托管_Docker_与_npm_两条路.pdf` 是早期验证 pdfgen 时留下的，
库里没有对应的 asset 记录，删不删都行。

---

## 4. 需要你拍板的事

### 4.1 「副业与变现」这个方向几乎空着

100 条素材里只有 1 条落到这个方向。相关性最低的 4 条是：

```
#103 相关性 2  Passenger 部署 Python 应用
#43  相关性 3  VPS 部署 Web 应用完整流程
#47  相关性 3  Stripe 收款集成
#24  相关性 4  FastAPI 生产化改造清单
```

分类器的判断是对的：这些是**基础设施 / 部署**类教程，既不是 AI 工具，
也不教怎么赚钱。暴露的是方向设置有空缺。两个选项：

- 把 `side-income` 的 description 写宽，把"独立开发者的部署与收款基建"算进去
- 新开一个「部署与基建」方向

定了之后跑 `python scripts/reclassify.py --all` 整批重路由，不用重新生成文案。

### 4.2 要不要 push

远端是 `git@githubdw3:dannyxweb3/tg-course-worker.git`。不确定它是公开还是私有。
提交里有 `scripts/urls_batch1.txt`（100 条采集链接）和 `assets/avatars/`，
不含任何密钥，但会暴露内容方向和运营意图。

### 4.3 `start.sh` 怎么办

要么加进 `.gitignore` 让它别再出现在 `git status` 里，要么删掉
（Linux 上有 `deploy/install.sh` 和 systemd，不需要它）。

---

## 5. 这次会话踩过、但从代码上看不出来的坑

CLAUDE.md 里已经有的（token 不入库、Telegram HTML 子集、callback_data 64 字节、
LF 换行、后台绑 127.0.0.1）这里不重复。补充几条：

**分类 prompt 被生成 schema 污染，静默丢掉 70% 的路由。**
`_task()` 会在任务模板后追加 `_output_format.md`（生成任务的 schema），
而 `task_classify.md` 自带输出定义 —— 两段互相矛盾的"严格输出 JSON"，
后一段经常赢，模型直接返回一篇文案。已修，并在 `classify()` 里加了守卫：
返回里没有 `scores`/`vertical` 就报错，不再静默当成"哪个方向都不沾边"。
**教训是：静默降级比报错危险得多**，这个 bug 藏了整整一批 100 条素材才被发现。

**SQLite 写锁会让脚本假死。** 批处理脚本和常驻服务同时连库，
没有 `PRAGMA busy_timeout` 就是无限干等，表现为脚本卡住且没有任何报错。
已在 schema 里加了 10 秒超时。在 Linux 上跑任何 `scripts/*.py` 之前，
**先想清楚服务是不是也在写库**。

**PDF 字体必须子集化。** PyMuPDF 内置的 `china-s` 整套嵌进去是 3.6MB，
`subset_fonts()` 之后 90KB。100 份就是 370MB 和 9MB 的差别。

**`file_id` 是绑 bot 的。** 生产 bot 收到文件拿到的 `file_id`，资料机用不了。
这就是为什么必须有仓库频道中转 —— 不是为了备份，是协议限制。

**userbot 发的消息带不了 inline 按钮。** 这条决定了发布身份必须是 bot。

---

## 6. 项目里的脚本都是干嘛的

```bash
scripts/bootstrap.py      # 空库引导，建第一套 bot/方向/频道。已经跑过，别再跑
scripts/batch_ingest.py   # 批量灌素材：URL 列表 → 抓取 → 分类 → 生成 → PDF → 待审核
scripts/probe_urls.py     # 只读探测链接能不能抽出正文。先筛再灌，别为抓不到的页面付 API 钱
scripts/reclassify.py     # 只重跑分类，不动文案和状态。改了方向描述或分类 prompt 之后用
scripts/make_avatars.py   # 重新生成 assets/avatars/ 里的头像
scripts/backup.sh         # 每日备份，丢 crontab。用 sqlite .backup，不会撞上 WAL
```

`scripts/urls_batch1.txt` 是已经跑完的那 100 条链接，留作记录。
重复跑 `batch_ingest.py` 是安全的，收过的会自动跳过。
