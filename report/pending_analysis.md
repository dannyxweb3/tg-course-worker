# 待分析列表（pending analysis）

> 生成于 2026-09-13 · 共 **275** 项（频道 204 · 群组 71）· 不含机器人


## 来源与筛选口径

采集自三个 Telegram 导航仓库的 README（**仅 HTTP，未用 telethon**）：

- `Henry-bai3006/TGgroup`（表格内含人数/类型，标记 **H**）
- `AZeC4/TelegramChannels`（标记 **C**）
- `AZeC4/TelegramGroup`（标记 **G**）

筛选规则：

1. **排除机器人**（用户名以 bot 结尾、搜索聚合 bot 如 jisou/soso 等）与邀请链接（`+`/`joinchat`）。
2. **人数 > 8000**：优先用 `t.me/s/` 或 `t.me/` 页解析的实时订阅/成员数（count_src=http）；
   预览被内容保护、HTTP 取不到数时，回退用 Henry 表格内的人数（count_src=list）。
3. **跳过半年内无更新 / 动态过少**：对**频道**，用 `t.me/s/` 页的最近消息时间判断，
   最后更新 >180 天或可见消息过少者已剔除；内容保护取不到 feed 的标 `protected/unknown`（保留，无法判断）。
   **群组**的活跃度无法通过 HTTP 判断，一律保留并标 `group/http-unknown`。
4. **跳过已分析过的**（report/ 下已有记录的，0 项泄漏）。

> ⚠️ 说明：
> - 列表按人数降序。**靠前的多为 Telegram 官方/全球性频道**（durov、telegram、contest、TgSticker 等，已标注 `TG官方/全球`）
>   及外国政要频道——若只做中文灰产竞品分析，可整体跳过这些。
> - 人数为抓取时点快照，仅供门槛过滤，非精确值。
> - 机器可读版见 [../data/qualified_http.tsv](../data/qualified_http.tsv)。

## 列表

| # | 用户名 | 类型 | 人数 | 数据源 | 活跃度 | 来源 | 备注 |
|--:|:--|:--|--:|:--|:--|:--|:--|
| 1 | [TelegramTips](https://t.me/TelegramTips) | 频道 | 10,988,042 | http | 16d/20posts | CG | TG官方/全球 |
| 2 | [durov](https://t.me/durov) | 频道 | 10,775,067 | http | 1d/20posts | CG | TG官方/全球 |
| 3 | [telegram](https://t.me/telegram) | 频道 | 9,565,251 | http | 17d/20posts | CG | TG官方/全球 |
| 4 | [telegramtipsAR](https://t.me/telegramtipsAR) | 频道 | 1,620,778 | http | 134d/20posts | CG | TG官方/全球 |
| 5 | [nicegramapp](https://t.me/nicegramapp) | 频道 | 1,578,991 | http | 2d/20posts | CG | TG官方/全球 |
| 6 | [telegramtipsES](https://t.me/telegramtipsES) | 频道 | 1,508,373 | http | 16d/20posts | CG | TG官方/全球 |
| 7 | [durov_russia](https://t.me/durov_russia) | 频道 | 986,364 | http | 11d/19posts | CG | TG官方/全球 |
| 8 | [plusmsgr](https://t.me/plusmsgr) | 频道 | 866,064 | http | 4d/20posts | CG | TG官方/全球 |
| 9 | [TgSticker](https://t.me/TgSticker) | 频道 | 791,422 | http | 0d/20posts | CG | TG官方/全球 |
| 10 | [telegramtipsbr](https://t.me/telegramtipsbr) | 频道 | 702,761 | http | 16d/20posts | CG | TG官方/全球 |
| 11 | [V_Zelenskiy_official](https://t.me/V_Zelenskiy_official) | 频道 | 672,408 | http | 0d/6posts | CG |  |
| 12 | [telegramtipsID](https://t.me/telegramtipsID) | 频道 | 452,661 | http | 6d/20posts | CG | TG官方/全球 |
| 13 | [TrumpJr](https://t.me/TrumpJr) | 频道 | 358,734 | http | 2d/20posts | CG |  |
| 14 | [contest](https://t.me/contest) | 频道 | 299,476 | http | 6d/20posts | CG | TG官方/全球 |
| 15 | [TestFlightCN](https://t.me/TestFlightCN) | 频道 | 281,982 | http | 0d/20posts | HCG |  |
| 16 | [BinanceChinese](https://t.me/BinanceChinese) | 群组 | 264,686 | http | group/http-unknown | CG |  |
| 17 | [XPlus_Channel](https://t.me/XPlus_Channel) | 频道 | 264,457 | http | 18d/20posts | CG |  |
| 18 | [TAndroidAPK](https://t.me/TAndroidAPK) | 频道 | 257,304 | http | 18d/20posts | CG |  |
| 19 | [qiqubaike](https://t.me/qiqubaike) | 频道 | 245,021 | http | protected/unknown | CG |  |
| 20 | [shmirziyoyev](https://t.me/shmirziyoyev) | 频道 | 245,017 | http | 0d/8posts | CG |  |
| 21 | [shareAliyun](https://t.me/shareAliyun) | 频道 | 202,091 | http | 0d/20posts | CG |  |
| 22 | [PicACG](https://t.me/PicACG) | 频道 | 191,335 | http | 148d/12posts | CG |  |
| 23 | [telegramtipsit](https://t.me/telegramtipsit) | 频道 | 183,884 | http | 16d/20posts | CG | TG官方/全球 |
| 24 | [AbiyAhmedAliofficial](https://t.me/AbiyAhmedAliofficial) | 频道 | 180,094 | http | 0d/13posts | CG |  |
| 25 | [appmew](https://t.me/appmew) | 频道 | 166,058 | http | 0d/18posts | HCG |  |
| 26 | [tnews365](https://t.me/tnews365) | 频道 | 163,902 | http | 0d/19posts | HCG |  |
| 27 | [xhqcankao](https://t.me/xhqcankao) | 频道 | 162,848 | http | 0d/20posts | CG |  |
| 28 | [TelegramES](https://t.me/TelegramES) | 频道 | 147,744 | http | 17d/20posts | CG | TG官方/全球 |
| 29 | [yunpanpan](https://t.me/yunpanpan) | 频道 | 142,044 | list | protected/unknown | HCG |  |
| 30 | [jichangtj](https://t.me/jichangtj) | 频道 | 134,067 | http | 0d/18posts | CG |  |
| 31 | [BotNews](https://t.me/BotNews) | 频道 | 131,211 | http | 19d/20posts | CG | TG官方/全球 |
| 32 | [science](https://t.me/science) | 频道 | 120,300 | http | 0d/19posts | CG | TG官方/全球 |
| 33 | [TelegramBR](https://t.me/TelegramBR) | 频道 | 115,747 | http | 17d/20posts | CG | TG官方/全球 |
| 34 | [woshadiao](https://t.me/woshadiao) | 频道 | 115,378 | http | 0d/19posts | HCG |  |
| 35 | [BotsArchive](https://t.me/BotsArchive) | 频道 | 110,096 | http | 4d/20posts | CG | TG官方/全球 |
| 36 | [inside1024](https://t.me/inside1024) | 频道 | 107,852 | http | 0d/18posts | H |  |
| 37 | [programmerjokes](https://t.me/programmerjokes) | 频道 | 107,152 | http | 1d/20posts | CG |  |
| 38 | [gebaopiCloud](https://t.me/gebaopiCloud) | 频道 | 101,014 | http | 0d/10posts | CG |  |
| 39 | [hezu2](https://t.me/hezu2) | 频道 | 100,407 | http | 0d/20posts | CG |  |
| 40 | [WidgetChannel](https://t.me/WidgetChannel) | 频道 | 99,398 | http | 0d/17posts | H |  |
| 41 | [ziyuanfeng59](https://t.me/ziyuanfeng59) | 频道 | 97,569 | http | protected/unknown | HCG |  |
| 42 | [Python](https://t.me/Python) | 群组 | 96,153 | http | group/http-unknown | CG |  |
| 43 | [Aliyundrive_Share_Channel](https://t.me/Aliyundrive_Share_Channel) | 频道 | 94,391 | list | protected/unknown | HCG |  |
| 44 | [RTErdogan](https://t.me/RTErdogan) | 频道 | 93,805 | http | 0d/16posts | CG |  |
| 45 | [ShortcutsCN](https://t.me/ShortcutsCN) | 频道 | 89,513 | http | 0d/20posts | CG |  |
| 46 | [dianying4K](https://t.me/dianying4K) | 频道 | 87,017 | http | 0d/20posts | CG |  |
| 47 | [times001](https://t.me/times001) | 频道 | 84,912 | http | -1d/8posts | CG |  |
| 48 | [tginfo](https://t.me/tginfo) | 频道 | 83,090 | http | 21d/20posts | CG |  |
| 49 | [TelegramArabia](https://t.me/TelegramArabia) | 频道 | 78,840 | http | 14d/20posts | CG | TG官方/全球 |
| 50 | [xinjingdaily](https://t.me/xinjingdaily) | 频道 | 77,503 | http | protected/unknown | CG |  |
| 51 | [CE_Observe](https://t.me/CE_Observe) | 频道 | 74,573 | http | 0d/20posts | CG |  |
| 52 | [designers](https://t.me/designers) | 频道 | 71,626 | http | 12d/19posts | CG |  |
| 53 | [hezu1](https://t.me/hezu1) | 群组 | 69,277 | http | group/http-unknown | CG |  |
| 54 | [NewlearnerChannel](https://t.me/NewlearnerChannel) | 频道 | 67,241 | http | 0d/13posts | CG |  |
| 55 | [alikuake](https://t.me/alikuake) | 频道 | 66,522 | list | protected/unknown | H |  |
| 56 | [WenAnBa](https://t.me/WenAnBa) | 频道 | 66,113 | http | 0d/17posts | H |  |
| 57 | [NobyDa](https://t.me/NobyDa) | 频道 | 63,276 | http | 1d/13posts | CG |  |
| 58 | [Readfine](https://t.me/Readfine) | 频道 | 63,273 | http | protected/unknown | HCG |  |
| 59 | [bnetanyahu](https://t.me/bnetanyahu) | 频道 | 58,200 | http | 1d/20posts | CG |  |
| 60 | [TelegramThemes](https://t.me/TelegramThemes) | 群组 | 57,979 | http | group/http-unknown | CG | TG官方/全球 |
| 61 | [TrendingStickers](https://t.me/TrendingStickers) | 频道 | 56,099 | http | 13d/20posts | CG |  |
| 62 | [EmbyPublic](https://t.me/EmbyPublic) | 群组 | 54,511 | http | group/http-unknown | CG |  |
| 63 | [QuanXApp](https://t.me/QuanXApp) | 群组 | 53,612 | http | group/http-unknown | CG |  |
| 64 | [vip115hot](https://t.me/vip115hot) | 频道 | 52,102 | http | -1d/20posts | CG |  |
| 65 | [three001](https://t.me/three001) | 群组 | 51,358 | http | group/http-unknown | CG |  |
| 66 | [asmrforme](https://t.me/asmrforme) | 频道 | 50,942 | http | protected/unknown | CG |  |
| 67 | [ReutersWorldChannel](https://t.me/ReutersWorldChannel) | 频道 | 49,855 | http | 56d/20posts | CG |  |
| 68 | [vps_xhq](https://t.me/vps_xhq) | 频道 | 49,585 | http | 10d/20posts | CG |  |
| 69 | [TGeBook](https://t.me/TGeBook) | 频道 | 49,120 | http | protected/unknown | H |  |
| 70 | [merlinclashcat](https://t.me/merlinclashcat) | 频道 | 47,602 | http | 63d/20posts | CG |  |
| 71 | [solidot](https://t.me/solidot) | 频道 | 47,296 | http | 1d/20posts | CG |  |
| 72 | [ShadowrocketNews](https://t.me/ShadowrocketNews) | 频道 | 46,671 | http | 2d/20posts | CG |  |
| 73 | [GoogleFans](https://t.me/GoogleFans) | 群组 | 45,443 | http | group/http-unknown | CG |  |
| 74 | [TestFlightX](https://t.me/TestFlightX) | 频道 | 44,667 | http | 95d/20posts | CG |  |
| 75 | [yunpanshare](https://t.me/yunpanshare) | 频道 | 42,714 | list | protected/unknown | H |  |
| 76 | [NekogramAPKs](https://t.me/NekogramAPKs) | 频道 | 41,575 | http | 12d/4posts | CG |  |
| 77 | [Lottery_home](https://t.me/Lottery_home) | 频道 | 41,535 | http | 9d/20posts | CG |  |
| 78 | [OutsightChina](https://t.me/OutsightChina) | 频道 | 41,267 | http | 0d/5posts | CG |  |
| 79 | [QuanXNews](https://t.me/QuanXNews) | 频道 | 40,970 | http | 0d/20posts | CG |  |
| 80 | [fufeikc](https://t.me/fufeikc) | 频道 | 40,727 | http | 2d/20posts | CG |  |
| 81 | [bigdongdongGroup](https://t.me/bigdongdongGroup) | 群组 | 40,167 | http | group/http-unknown | CG |  |
| 82 | [opencfdchannel](https://t.me/opencfdchannel) | 频道 | 39,971 | list | protected/unknown | HCG |  |
| 83 | [StickerGroup](https://t.me/StickerGroup) | 群组 | 39,609 | http | group/http-unknown | CG |  |
| 84 | [Loon0x00](https://t.me/Loon0x00) | 群组 | 39,589 | http | group/http-unknown | CG |  |
| 85 | [lihaiba](https://t.me/lihaiba) | 频道 | 39,066 | http | 3d/20posts | HCG |  |
| 86 | [tgzhcn](https://t.me/tgzhcn) | 群组 | 38,379 | http | group/http-unknown | H |  |
| 87 | [sspai](https://t.me/sspai) | 频道 | 38,160 | http | 1d/20posts | HCG |  |
| 88 | [weekly_books](https://t.me/weekly_books) | 频道 | 38,119 | http | 0d/17posts | CG |  |
| 89 | [SecHorse](https://t.me/SecHorse) | 频道 | 37,582 | http | -1d/5posts | CG |  |
| 90 | [theblockbeats](https://t.me/theblockbeats) | 频道 | 37,453 | http | 0d/20posts | H |  |
| 91 | [AppleNuts](https://t.me/AppleNuts) | 频道 | 36,961 | http | 0d/20posts | CG |  |
| 92 | [zaobaosg](https://t.me/zaobaosg) | 频道 | 36,828 | http | 0d/20posts | CG |  |
| 93 | [gephusers](https://t.me/gephusers) | 群组 | 36,779 | http | group/http-unknown | CG |  |
| 94 | [sizukon](https://t.me/sizukon) | 频道 | 36,527 | http | 88d/6posts | H |  |
| 95 | [kejiqu](https://t.me/kejiqu) | 频道 | 36,415 | http | 0d/20posts | H |  |
| 96 | [douban_read](https://t.me/douban_read) | 频道 | 36,201 | http | 158d/11posts | CG |  |
| 97 | [thinkpositivewords](https://t.me/thinkpositivewords) | 频道 | 36,163 | http | 1d/20posts | CG |  |
| 98 | [jike_collection](https://t.me/jike_collection) | 频道 | 35,800 | http | 0d/14posts | HCG |  |
| 99 | [LptTech](https://t.me/LptTech) | 频道 | 35,504 | http | 42d/18posts | H |  |
| 100 | [niuyueshibao_rss](https://t.me/niuyueshibao_rss) | 频道 | 34,142 | http | 1d/20posts | CG |  |
| 101 | [M_Team_Chat](https://t.me/M_Team_Chat) | 群组 | 31,172 | http | group/http-unknown | CG |  |
| 102 | [tginfoen](https://t.me/tginfoen) | 频道 | 30,857 | http | 18d/20posts | CG |  |
| 103 | [projectXtls](https://t.me/projectXtls) | 频道 | 29,913 | http | 0d/20posts | CG |  |
| 104 | [hacker_news_feed](https://t.me/hacker_news_feed) | 频道 | 29,607 | http | 0d/20posts | CG |  |
| 105 | [OnePlus](https://t.me/OnePlus) | 频道 | 29,519 | http | 58d/18posts | CG |  |
| 106 | [zaproshare](https://t.me/zaproshare) | 频道 | 29,172 | http | 1d/20posts | HCG |  |
| 107 | [XiangxiuNB](https://t.me/XiangxiuNB) | 频道 | 28,962 | list | protected/unknown | H |  |
| 108 | [beijingz](https://t.me/beijingz) | 群组 | 28,881 | http | group/http-unknown | CG |  |
| 109 | [ruheyushadiaoxiangchu](https://t.me/ruheyushadiaoxiangchu) | 频道 | 28,805 | http | 0d/20posts | HCG |  |
| 110 | [TGgeek](https://t.me/TGgeek) | 频道 | 28,783 | http | protected/unknown | CG |  |
| 111 | [Meitian](https://t.me/Meitian) | 频道 | 28,705 | http | 8d/15posts | HCG |  |
| 112 | [QuanX_API](https://t.me/QuanX_API) | 频道 | 28,544 | http | 119d/20posts | CG |  |
| 113 | [surfboardnews](https://t.me/surfboardnews) | 频道 | 28,416 | http | 11d/20posts | CG |  |
| 114 | [iyouport](https://t.me/iyouport) | 频道 | 27,846 | http | 2d/13posts | CG |  |
| 115 | [bbczhongwen_rss](https://t.me/bbczhongwen_rss) | 频道 | 26,853 | http | 0d/20posts | CG |  |
| 116 | [PublicTestGroup](https://t.me/PublicTestGroup) | 群组 | 26,731 | http | group/http-unknown | CG |  |
| 117 | [bookusefor3](https://t.me/bookusefor3) | 频道 | 26,639 | http | protected/unknown | HCG |  |
| 118 | [gouwu](https://t.me/gouwu) | 群组 | 26,594 | http | group/http-unknown | CG |  |
| 119 | [giantcutie6688](https://t.me/giantcutie6688) | 群组 | 26,564 | http | group/http-unknown | CG |  |
| 120 | [BotTalk](https://t.me/BotTalk) | 群组 | 26,504 | http | group/http-unknown | CG |  |
| 121 | [Hao12News](https://t.me/Hao12News) | 频道 | 26,364 | http | 1d/20posts | H |  |
| 122 | [GIFgroupTW](https://t.me/GIFgroupTW) | 群组 | 25,760 | http | group/http-unknown | CG |  |
| 123 | [jin10light](https://t.me/jin10light) | 频道 | 25,734 | http | -1d/20posts | H |  |
| 124 | [BaccanoSoul](https://t.me/BaccanoSoul) | 频道 | 25,651 | http | 0d/20posts | CG |  |
| 125 | [jinan_tg](https://t.me/jinan_tg) | 群组 | 25,620 | http | group/http-unknown | CG |  |
| 126 | [v2rayN](https://t.me/v2rayN) | 群组 | 25,175 | http | group/http-unknown | CG |  |
| 127 | [nexitallyusers](https://t.me/nexitallyusers) | 群组 | 24,963 | http | group/http-unknown | CG |  |
| 128 | [loveapps](https://t.me/loveapps) | 群组 | 24,706 | http | group/http-unknown | CG |  |
| 129 | [ACL4SSR](https://t.me/ACL4SSR) | 频道 | 24,570 | http | 96d/20posts | CG |  |
| 130 | [ngcss](https://t.me/ngcss) | 群组 | 24,355 | http | group/http-unknown | CG |  |
| 131 | [speedcentre](https://t.me/speedcentre) | 频道 | 24,276 | http | 0d/15posts | CG |  |
| 132 | [VodStore](https://t.me/VodStore) | 群组 | 23,358 | http | group/http-unknown | H |  |
| 133 | [TelegramPassport](https://t.me/TelegramPassport) | 频道 | 23,287 | http | protected/unknown | CG | TG官方/全球 |
| 134 | [wikipedia_zh_n](https://t.me/wikipedia_zh_n) | 群组 | 22,767 | http | group/http-unknown | CG |  |
| 135 | [pythonzh](https://t.me/pythonzh) | 群组 | 22,675 | http | group/http-unknown | HCG |  |
| 136 | [voice_google](https://t.me/voice_google) | 频道 | 22,633 | http | 27d/18posts | CG |  |
| 137 | [yeqingjie_GJG666](https://t.me/yeqingjie_GJG666) | 频道 | 22,269 | http | 27d/20posts | H |  |
| 138 | [Qikan2023](https://t.me/Qikan2023) | 频道 | 22,245 | list | protected/unknown | H |  |
| 139 | [creativemotion](https://t.me/creativemotion) | 频道 | 21,678 | http | 0d/12posts | CG |  |
| 140 | [google_drive](https://t.me/google_drive) | 群组 | 21,514 | http | group/http-unknown | HCG |  |
| 141 | [moeisland](https://t.me/moeisland) | 频道 | 21,218 | http | 0d/19posts | H |  |
| 142 | [TimeHorizonX](https://t.me/TimeHorizonX) | 频道 | 20,800 | http | 2d/19posts | H |  |
| 143 | [titan_pain](https://t.me/titan_pain) | 频道 | 20,742 | http | 0d/16posts | H |  |
| 144 | [hao123f](https://t.me/hao123f) | 群组 | 20,517 | http | group/http-unknown | CG |  |
| 145 | [YXHMd](https://t.me/YXHMd) | 频道 | 20,268 | http | 1d/20posts | H |  |
| 146 | [PornNFHD](https://t.me/PornNFHD) | 频道 | 20,235 | list | protected/unknown | H |  |
| 147 | [AndroidThemesGroup](https://t.me/AndroidThemesGroup) | 群组 | 20,098 | http | group/http-unknown | CG |  |
| 148 | [zuanke8](https://t.me/zuanke8) | 频道 | 19,914 | http | 169d/20posts | HCG |  |
| 149 | [lover_links](https://t.me/lover_links) | 频道 | 19,775 | http | 0d/16posts | CG |  |
| 150 | [ClashR_for_Windows_Channel](https://t.me/ClashR_for_Windows_Channel) | 频道 | 19,690 | http | 1d/20posts | CG |  |
| 151 | [jlpahz](https://t.me/jlpahz) | 频道 | 19,619 | http | protected/unknown | H |  |
| 152 | [PinYunPs](https://t.me/PinYunPs) | 频道 | 19,545 | http | 0d/4posts | CG |  |
| 153 | [V2EXPro](https://t.me/V2EXPro) | 群组 | 19,464 | http | group/http-unknown | HCG |  |
| 154 | [daily5kong](https://t.me/daily5kong) | 频道 | 19,254 | http | 13d/20posts | CG |  |
| 155 | [nicegramchat](https://t.me/nicegramchat) | 群组 | 18,970 | http | group/http-unknown | CG |  |
| 156 | [bookusefor2](https://t.me/bookusefor2) | 频道 | 18,753 | http | protected/unknown | HCG |  |
| 157 | [magazinesclubnew](https://t.me/magazinesclubnew) | 频道 | 18,479 | http | 0d/20posts | H |  |
| 158 | [NianticOfficial](https://t.me/NianticOfficial) | 频道 | 18,230 | http | 1d/20posts | CG |  |
| 159 | [misakatech](https://t.me/misakatech) | 频道 | 18,169 | http | 17d/20posts | HCG |  |
| 160 | [ruanlu](https://t.me/ruanlu) | 群组 | 18,009 | http | group/http-unknown | CG |  |
| 161 | [limboprossr](https://t.me/limboprossr) | 频道 | 17,965 | http | 0d/20posts | CG |  |
| 162 | [ziyuanfengxiang59](https://t.me/ziyuanfengxiang59) | 群组 | 17,755 | list | group/http-unknown | HCG |  |
| 163 | [lychee_wood](https://t.me/lychee_wood) | 频道 | 17,740 | http | -1d/18posts | CG |  |
| 164 | [pythontelegrambotchannel](https://t.me/pythontelegrambotchannel) | 频道 | 17,480 | http | 93d/20posts | CG |  |
| 165 | [Licensesss](https://t.me/Licensesss) | 频道 | 17,378 | http | 0d/20posts | CG |  |
| 166 | [zrj96](https://t.me/zrj96) | 频道 | 17,087 | http | 0d/18posts | CG |  |
| 167 | [leehsienloong](https://t.me/leehsienloong) | 频道 | 16,851 | http | 2d/20posts | CG |  |
| 168 | [ibetame](https://t.me/ibetame) | 群组 | 16,737 | http | group/http-unknown | HCG |  |
| 169 | [zhihuribao_rss](https://t.me/zhihuribao_rss) | 频道 | 16,664 | http | 0d/20posts | CG |  |
| 170 | [tgx_perfection](https://t.me/tgx_perfection) | 群组 | 16,462 | http | group/http-unknown | CG |  |
| 171 | [iingtw](https://t.me/iingtw) | 频道 | 16,365 | http | 2d/8posts | CG |  |
| 172 | [woniubuchuiniu](https://t.me/woniubuchuiniu) | 频道 | 16,305 | list | protected/unknown | H |  |
| 173 | [cool_scripts](https://t.me/cool_scripts) | 频道 | 16,266 | http | 1d/18posts | CG |  |
| 174 | [SteamNy](https://t.me/SteamNy) | 频道 | 16,181 | http | 0d/20posts | CG |  |
| 175 | [pdcn2](https://t.me/pdcn2) | 群组 | 15,987 | http | group/http-unknown | CG |  |
| 176 | [wangvpn_user_chat](https://t.me/wangvpn_user_chat) | 群组 | 15,881 | http | group/http-unknown | CG |  |
| 177 | [projectXray](https://t.me/projectXray) | 群组 | 15,808 | http | group/http-unknown | CG |  |
| 178 | [sharecentre](https://t.me/sharecentre) | 频道 | 15,704 | http | 0d/20posts | CG |  |
| 179 | [translation_zhcncc](https://t.me/translation_zhcncc) | 群组 | 15,606 | http | group/http-unknown | CG |  |
| 180 | [tgfiles](https://t.me/tgfiles) | 频道 | 15,584 | http | protected/unknown | CG |  |
| 181 | [wublock](https://t.me/wublock) | 频道 | 15,486 | http | 0d/20posts | HCG |  |
| 182 | [steamsteam](https://t.me/steamsteam) | 频道 | 15,387 | http | 2d/20posts | CG |  |
| 183 | [stopCA](https://t.me/stopCA) | 频道 | 15,293 | http | -1d/20posts | CG |  |
| 184 | [IsisWatch](https://t.me/IsisWatch) | 频道 | 15,282 | http | -1d/20posts | CG |  |
| 185 | [shendu666](https://t.me/shendu666) | 频道 | 15,155 | list | protected/unknown | H |  |
| 186 | [askahh](https://t.me/askahh) | 频道 | 15,149 | http | 127d/11posts | CG |  |
| 187 | [shuangyunews_rss](https://t.me/shuangyunews_rss) | 频道 | 15,131 | http | 1d/20posts | CG |  |
| 188 | [dlbmeng1](https://t.me/dlbmeng1) | 频道 | 15,129 | http | protected/unknown | CG |  |
| 189 | [openwrt_flippy](https://t.me/openwrt_flippy) | 频道 | 14,925 | http | 4d/4posts | HCG |  |
| 190 | [ksc666](https://t.me/ksc666) | 频道 | 14,910 | http | 2d/18posts | H |  |
| 191 | [BooksThatMakeYouThink](https://t.me/BooksThatMakeYouThink) | 频道 | 14,660 | http | protected/unknown | CG |  |
| 192 | [Orzmini](https://t.me/Orzmini) | 频道 | 14,632 | http | 33d/19posts | CG |  |
| 193 | [natgeomedia](https://t.me/natgeomedia) | 频道 | 14,557 | http | 0d/20posts | HCG |  |
| 194 | [liyuans](https://t.me/liyuans) | 频道 | 14,321 | http | 3d/18posts | CG |  |
| 195 | [plusmsgrchat](https://t.me/plusmsgrchat) | 群组 | 14,264 | http | group/http-unknown | CG |  |
| 196 | [ixsk0](https://t.me/ixsk0) | 频道 | 13,896 | list | protected/unknown | H |  |
| 197 | [pixivshare](https://t.me/pixivshare) | 频道 | 13,867 | http | 20d/19posts | H |  |
| 198 | [hnzzs](https://t.me/hnzzs) | 群组 | 13,771 | http | group/http-unknown | CG |  |
| 199 | [macos_stable_updates_files](https://t.me/macos_stable_updates_files) | 频道 | 13,771 | http | protected/unknown | CG |  |
| 200 | [kxswjs](https://t.me/kxswjs) | 群组 | 13,495 | http | group/http-unknown | CG |  |
| 201 | [meiguozhiyin_rss](https://t.me/meiguozhiyin_rss) | 频道 | 13,484 | http | 0d/20posts | CG |  |
| 202 | [Pojieapp](https://t.me/Pojieapp) | 频道 | 13,468 | http | -1d/20posts | CG |  |
| 203 | [googlevoice](https://t.me/googlevoice) | 群组 | 13,396 | http | group/http-unknown | HCG |  |
| 204 | [pixelexperiencechat](https://t.me/pixelexperiencechat) | 群组 | 13,324 | http | group/http-unknown | CG |  |
| 205 | [alypzyhzq](https://t.me/alypzyhzq) | 群组 | 13,071 | list | group/http-unknown | H |  |
| 206 | [what_youread](https://t.me/what_youread) | 群组 | 12,955 | http | group/http-unknown | HCG |  |
| 207 | [peekfun](https://t.me/peekfun) | 频道 | 12,937 | http | 9d/20posts | HCG |  |
| 208 | [JISFW](https://t.me/JISFW) | 频道 | 12,752 | http | 0d/15posts | CG |  |
| 209 | [newmobilelife](https://t.me/newmobilelife) | 频道 | 12,626 | http | 0d/20posts | HCG |  |
| 210 | [EqualLeaks](https://t.me/EqualLeaks) | 频道 | 12,621 | http | 2d/12posts | CG |  |
| 211 | [tdlibchat](https://t.me/tdlibchat) | 群组 | 12,605 | http | group/http-unknown | CG |  |
| 212 | [projectv2ray](https://t.me/projectv2ray) | 群组 | 12,570 | http | group/http-unknown | CG |  |
| 213 | [EZwalls](https://t.me/EZwalls) | 频道 | 12,567 | http | 95d/20posts | CG |  |
| 214 | [rsshub](https://t.me/rsshub) | 群组 | 12,563 | http | group/http-unknown | HCG |  |
| 215 | [Notionso](https://t.me/Notionso) | 群组 | 12,412 | http | group/http-unknown | HCG |  |
| 216 | [xuehuashe](https://t.me/xuehuashe) | 频道 | 12,283 | http | 9d/20posts | HCG |  |
| 217 | [TelegramIT](https://t.me/TelegramIT) | 频道 | 11,969 | http | 17d/20posts | CG | TG官方/全球 |
| 218 | [sockboom](https://t.me/sockboom) | 群组 | 11,900 | http | group/http-unknown | CG |  |
| 219 | [gate_io](https://t.me/gate_io) | 群组 | 11,896 | http | group/http-unknown | CG |  |
| 220 | [vpscang](https://t.me/vpscang) | 频道 | 11,818 | http | 9d/20posts | CG |  |
| 221 | [ioshkj007](https://t.me/ioshkj007) | 群组 | 11,800 | http | group/http-unknown | CG |  |
| 222 | [ovov1234](https://t.me/ovov1234) | 频道 | 11,753 | http | 155d/20posts | H |  |
| 223 | [moepic](https://t.me/moepic) | 频道 | 11,558 | http | 56d/16posts | H |  |
| 224 | [contests](https://t.me/contests) | 群组 | 11,543 | http | group/http-unknown | CG |  |
| 225 | [githubtrending](https://t.me/githubtrending) | 频道 | 11,497 | http | 0d/20posts | CG |  |
| 226 | [kanxiaojiejie](https://t.me/kanxiaojiejie) | 频道 | 11,492 | http | 3d/11posts | H |  |
| 227 | [nasfan](https://t.me/nasfan) | 群组 | 11,412 | http | group/http-unknown | HCG |  |
| 228 | [lutouzhongwen_rss](https://t.me/lutouzhongwen_rss) | 频道 | 11,390 | http | 0d/20posts | CG |  |
| 229 | [english_learning_discuss](https://t.me/english_learning_discuss) | 频道 | 11,218 | http | 128d/15posts | H |  |
| 230 | [illusory_world](https://t.me/illusory_world) | 频道 | 10,970 | http | 1d/19posts | CG |  |
| 231 | [HellCellZC123](https://t.me/HellCellZC123) | 频道 | 10,845 | http | 0d/12posts | CG |  |
| 232 | [zhujiwiki_info](https://t.me/zhujiwiki_info) | 频道 | 10,684 | http | 0d/20posts | HCG |  |
| 233 | [testflights](https://t.me/testflights) | 频道 | 10,655 | http | 4d/20posts | CG |  |
| 234 | [tg_InternetSecurity](https://t.me/tg_InternetSecurity) | 频道 | 10,654 | http | 0d/20posts | CG |  |
| 235 | [unigram](https://t.me/unigram) | 频道 | 10,492 | http | 36d/20posts | CG |  |
| 236 | [iOS_jailbreaking](https://t.me/iOS_jailbreaking) | 群组 | 10,472 | http | group/http-unknown | CG |  |
| 237 | [nyt_bilingual](https://t.me/nyt_bilingual) | 频道 | 10,348 | http | 124d/20posts | H |  |
| 238 | [chavyscripts](https://t.me/chavyscripts) | 频道 | 10,207 | http | 59d/17posts | CG |  |
| 239 | [pythontelegrambotgroup](https://t.me/pythontelegrambotgroup) | 群组 | 10,018 | http | group/http-unknown | CG |  |
| 240 | [MRHXPJGG](https://t.me/MRHXPJGG) | 频道 | 9,989 | http | 51d/18posts | CG |  |
| 241 | [CGSFW](https://t.me/CGSFW) | 频道 | 9,978 | http | protected/unknown | HCG |  |
| 242 | [durovschat](https://t.me/durovschat) | 群组 | 9,715 | http | group/http-unknown | CG |  |
| 243 | [viatg](https://t.me/viatg) | 群组 | 9,711 | http | group/http-unknown | CG |  |
| 244 | [sg_rss](https://t.me/sg_rss) | 频道 | 9,641 | http | protected/unknown | CG |  |
| 245 | [LetITFlyW](https://t.me/LetITFlyW) | 频道 | 9,589 | http | 0d/20posts | HCG |  |
| 246 | [secretofbody_degist](https://t.me/secretofbody_degist) | 频道 | 9,503 | http | protected/unknown | CG |  |
| 247 | [XiaoZhangDuBao](https://t.me/XiaoZhangDuBao) | 频道 | 9,468 | http | 0d/20posts | HCG |  |
| 248 | [Newbie_Chat](https://t.me/Newbie_Chat) | 群组 | 9,427 | http | group/http-unknown | HCG |  |
| 249 | [WenAnGuan_botjihuo](https://t.me/WenAnGuan_botjihuo) | 频道 | 9,393 | http | 94d/20posts | H |  |
| 250 | [tgbetachat](https://t.me/tgbetachat) | 群组 | 9,193 | http | group/http-unknown | CG |  |
| 251 | [sepiansousuo](https://t.me/sepiansousuo) | 群组 | 9,086 | http | group/http-unknown | G |  |
| 252 | [qiankeji](https://t.me/qiankeji) | 群组 | 9,080 | http | group/http-unknown | CG |  |
| 253 | [yunspeedtest](https://t.me/yunspeedtest) | 频道 | 9,048 | http | 0d/10posts | CG |  |
| 254 | [outvivid](https://t.me/outvivid) | 频道 | 9,003 | http | 0d/20posts | HCG |  |
| 255 | [MemesTelegram](https://t.me/MemesTelegram) | 频道 | 8,917 | http | 102d/20posts | CG |  |
| 256 | [Javaer](https://t.me/Javaer) | 群组 | 8,882 | http | group/http-unknown | HCG |  |
| 257 | [tg_x64](https://t.me/tg_x64) | 频道 | 8,721 | http | 1d/8posts | CG |  |
| 258 | [xinjiyuan9](https://t.me/xinjiyuan9) | 频道 | 8,626 | http | 0d/20posts | CG |  |
| 259 | [fnnew](https://t.me/fnnew) | 频道 | 8,563 | http | 0d/20posts | CG |  |
| 260 | [lumingguandj](https://t.me/lumingguandj) | 频道 | 8,552 | http | protected/unknown | HCG |  |
| 261 | [NewlearnerGroup](https://t.me/NewlearnerGroup) | 群组 | 8,480 | http | group/http-unknown | HCG |  |
| 262 | [vitamineEpodcast](https://t.me/vitamineEpodcast) | 频道 | 8,476 | http | 31d/20posts | HCG |  |
| 263 | [breakingnews_t](https://t.me/breakingnews_t) | 频道 | 8,458 | http | 4d/20posts | CG |  |
| 264 | [SSUnion](https://t.me/SSUnion) | 群组 | 8,437 | http | group/http-unknown | CG |  |
| 265 | [macapp_channel](https://t.me/macapp_channel) | 频道 | 8,388 | http | 2d/14posts | H |  |
| 266 | [readhub_cn](https://t.me/readhub_cn) | 频道 | 8,353 | http | 0d/20posts | HCG |  |
| 267 | [rvalue_daily](https://t.me/rvalue_daily) | 频道 | 8,331 | http | 1d/20posts | CG |  |
| 268 | [shufm](https://t.me/shufm) | 群组 | 8,325 | http | group/http-unknown | HCG |  |
| 269 | [magazinesclub](https://t.me/magazinesclub) | 频道 | 8,300 | http | protected/unknown | HCG |  |
| 270 | [ACGStickers](https://t.me/ACGStickers) | 频道 | 8,299 | http | 34d/20posts | CG |  |
| 271 | [dockertutorial](https://t.me/dockertutorial) | 群组 | 8,287 | http | group/http-unknown | HCG |  |
| 272 | [youganhuo](https://t.me/youganhuo) | 频道 | 8,285 | http | protected/unknown | CG |  |
| 273 | [soupianshenqibar](https://t.me/soupianshenqibar) | 群组 | 8,106 | http | group/http-unknown | G |  |
| 274 | [LinsBookA](https://t.me/LinsBookA) | 频道 | 8,023 | http | 2d/19posts | HCG |  |
| 275 | [XinHaNewsAgency](https://t.me/XinHaNewsAgency) | 频道 | 8,011 | http | 4d/9posts | CG |  |

