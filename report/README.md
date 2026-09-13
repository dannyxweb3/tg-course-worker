# TG 频道分析 —— 目录约定

竞品 Telegram **频道与群**的只读调研产出。数据来源是
[scripts/tg_recon.py](../scripts/tg_recon.py)（Telethon，user 账号，只读）
或 `t.me/s/` 公开预览页。

## 文件布局

```
report/
  index.json          清单 + 对比表 + 结论。UI 列表页读这个就够
  <slug>.json         单个频道/群的结构化指标（UI 渲染表格、图表用）
  <slug>.md           单个频道/群的完整分析正文（Markdown）
  build_index.py      重建 index.json 的脚本
  README.md           本文件
```

### ⚠️ index.json 是派生文件，不要手写

加一个频道只需要放进 `<slug>.json` + `<slug>.md`，然后跑：

```bash
conda run -n tg-course-worker python report/build_index.py
```

它扫目录重建 `channels` 和 `comparison`，每个频道的数字全部从
`<slug>.json` 读。叙事性字段（headline / conclusions / disclaimer /
content_warning / schema_notes）是脚本里的常量，改文案改脚本。

**报告只做分析，不产出「可借鉴 / 可迁移到本项目」这类结论。**
曾经有过 `applicable_to_project` / `not_applicable` 两个索引字段和每条
记录的 `takeaways`，已全部移除，写新报告时不要再加。

**为什么非要有这个脚本**：多个会话会并发往 `report/` 里写分析。
手工重排 `channels` 列表曾经把别的会话刚写进来的三条记录挤掉过一次。
扫目录生成就不会再有这个问题——所以**别再手工编辑 index.json**。

展示顺序由脚本里的 `ORDER` 常量控制；没列进 `ORDER` 的 slug 会按名字
排在后面，不会被丢掉。

`<slug>` 就是频道或群的 username，和 `data/recon/<slug>.jsonl` 一一对应。

每个 `<slug>.json` 还有一个 `growth_short` 字段——涨粉方式的短标签，
给对比表和卡片用；完整描述在 `implementation.growth`。

## 给写 UI 的会话

**1. 列表页读 `index.json`，详情页读 `<slug>.json` + `<slug>.md`。**
所有数字都在 JSON 里，不要去正则解析 Markdown。

**2. 本仓库没有装 Markdown 渲染库。** `requirements.txt` 里没有
`markdown` / `mistune` / `markdown-it-py`，环境里也没有。两条路：

- 加一个依赖（推荐 `markdown`，纯 Python 无编译）。记得同步
  `requirements.txt` 和 `environment.yml`
- 或者只渲染 `<slug>.json`，把 `.md` 当纯文本放进 `<pre>`

渲染 Markdown 时**必须转义 HTML**（`markdown` 包默认不转义原始 HTML）。
正文里引用了竞品频道的原始广告文案，当成不可信输入处理。

**3. `report/` 在版本库里，但它引用的原始数据不在。**
本目录会随代码一起提交、一起部署，UI 可以假定它存在。但正文里链到的
`data/recon/*.jsonl` 原始 dump 属于 `data/`，整个在 `.gitignore` 里，
服务器上不会有。所以：

- 不要让 UI 去读 `data/recon/*.jsonl`，只读本目录的 `.json` 和 `.md`
- Markdown 里指向 dump 的链接在服务器上是断的，渲染时别校验可达性
- 仍然建议 UI 能兜住 "index.json 缺失 / channels 为空" 的情况，不要 500

**4. schema 版本在 `index.json.schema_version`，当前 `3`。** 字段有增减就 +1。
版本说明在 `index.json.schema_notes`。

**4b. v3 新增了顶层 `growth` 维度（增长策略）。** 每条记录的分析维度顺序是
实现技术思路 → 增长策略 → 成本 → 收益 → 法律风险，JSON 里的字段顺序与之一致
（`implementation` → `growth` → `cost` → `revenue` → `risk`）。`growth` 的结构：

| 字段 | 说明 |
|---|---|
| `strategy` | 一句话概括 |
| `paid_acquisition` | `none` / `subs` / `engagement` / `exchange` / `mixed` / `unknown` |
| `mechanisms[]` | `{name, evidence, note}`，逐条增长手段 + 证据 |
| `signals{}` | 支撑判断的数字（自由键，因号而异） |
| `assessment` | 判读结论，含天花板与失败原因 |
| `derived_from` | 仅部分记录有。表示该条不是原始分析，增长结论由已有字段推导 |

`paid_acquisition` 已提到 `index.channels[]` 和对比表，适合做筛选与配色。
它和 ERR 的相关性是整份报告最强的规律：**`none` 基本对应高 ERR，
`exchange` / `subs` / `mixed` 基本对应 ERR 塌陷。**

**5. 频道和群不是一回事，渲染前先判 `kind`。**
`kind` 取值 `channel` 或 `group`。群（megagroup）**没有 per-message 阅读量**，
所以群记录的 `median_views` / `err_pct` 一律是 `null`，`views_available` 为 `false`。
拿 ERR 去套群会得出错误结论。群改看这两个字段：

- `metrics.online_pct` —— 在线数 / 成员数，判真实活跃
- `metrics.bot_share_pct` —— bot 消息占总消息的比例，判它是社区还是机器

对比表 `index.comparison` 里，阅读量相关的行对群填的是 `—`。

**6. 有一条内容警告，必须遵守。** 见 `index.json.content_warning`。
`jisou771` 承载的广告类目包含社工库开盒、线下性交易招揽、境外博彩与成人 AI 换脸。
**报告正文刻意没有引用这些原文**，分类描述即可说明问题。
UI 不要去读或显示 `data/recon/jisou771.jsonl` 的原始消息内容。

## 字段说明（`<slug>.json`）

| 字段 | 说明 |
|---|---|
| `metrics.err_pct` | 中位阅读 / 订阅数。**最重要的单一指标**，判断粉丝真假 |
| `metrics.forwards_per_post` | 自然扩散能力。< 1 基本等于没有 |
| `metrics.confidence` | `high` = Telethon 全量拉取；`medium` = web 预览抽样 |
| `metrics.views_available` | `false` 表示该记录是群，阅读量类字段全为 `null` |
| `metrics.online_pct` | 群专用。在线/成员，判真实活跃 |
| `metrics.bot_share_pct` | 群专用。bot 消息占比，> 50% 说明是机器驱动 |
| `revenue.est_scope` | 存在时表示估算只覆盖部分范围（如只算单个群的可归因部分） |
| `cost.owner_recurring_cny_month` | 存在时表示 `cost.recurring_cny_month` 记的是上游平台成本，横向对比要用这个自担口径 |
| `growth.paid_acquisition` | 增长质量的第一眼指标，见上文 4b |
| `analysis_scope` | 存在时表示该记录按要求省略了某些维度（如不含可迁移方法），不是数据缺失 |
| `cost.*_cny` / `revenue.*_cny` | 一律 `[下限, 上限]` 两元数组，人民币 |
| `revenue.streams[].confidence` | 该条变现路径的证据强度 |
| `risk.level` | `low` / `medium` / `high` / `criminal` |

`criminal` 表示该频道/群的业务在中国大陆属于刑事范畴（不只是民事侵权），
UI 上建议用醒目颜色标出来。四条记录里有三条是这一档。
