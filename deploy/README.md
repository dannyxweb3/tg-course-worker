# 部署

装服务用第一章或第二章，**二选一**；第三章（nginx）是可选的，
只有想让管理后台脱离 SSH 隧道访问才需要。
**systemd 是默认推荐**：机器上只多出一个 venv，升级就是再跑一次
`install.sh`，不需要 Docker。

```
deploy/
  install.sh                        一键安装 / 升级（幂等，可反复跑）
  restart.sh                        重启服务（一行）
  tg-course-worker.service          systemd unit 模板
  nginx/tg-course-worker.conf       反向代理配置（可选，见第三章）
```

## 一、systemd（推荐）

```bash
git clone <repo> && cd tg-course-worker
sudo deploy/install.sh
```

脚本干这些事：

1. 装系统依赖（`ca-certificates tzdata sqlite3 rsync libxml2 libxslt1.1`）
2. 找 Python 3.11+，没有就尝试装 `python3.12`
3. 建系统账号 `tgworker`（不能登录、没有家目录）
4. 同步代码到 `/opt/tg-course-worker`
5. 建 venv 并装 `requirements.txt`
6. 渲染 systemd unit、`daemon-reload`、`enable`
7. 把重启脚本装到 `/usr/local/bin/tg-course-worker-restart`

第一次跑完会生成 `.env` 但**不启动服务**（里面还是示例值）。按提示走完三步：

```bash
sudo -e /opt/tg-course-worker/.env          # 1. 填配置
sudo -u tgworker /opt/tg-course-worker/.venv/bin/python \
     /opt/tg-course-worker/scripts/bootstrap.py   # 2. 建第一套 bot/方向/频道
sudo systemctl start tg-course-worker       # 3. 启动
```

### 升级

```bash
cd <repo> && git pull && sudo deploy/install.sh
```

再跑一次就是滚动更新：代码同步、依赖更新、服务重启。
`.env`、`data/`、`logs/` 不会被动。删掉的模块会被 `rsync --delete` 清掉，
不会留下上个版本的残骸。

服务当时没在运行的话，脚本**不会**替你启动——多半是配置还没填完，
这时候硬启只会失败得莫名其妙。

### 日常操作

```bash
tg-course-worker-restart                      # 重启（改完 .env 或 prompt 后）
journalctl -u tg-course-worker -f             # 看日志
systemctl status tg-course-worker             # 看状态
sudo systemctl stop tg-course-worker          # 停
```

应用自己还会往 `/opt/tg-course-worker/logs/worker.log` 写一份，按天轮转留 14 天。

### 访问管理后台

后台只绑 `127.0.0.1`。**默认走 SSH 隧道，不需要 nginx**：

```bash
ssh -L 8080:127.0.0.1:8080 <你>@<服务器>
```

然后浏览器开 `http://127.0.0.1:8080`。

要在手机上用、或者要给别人开权限，见下面的
[三、用 nginx 对外暴露后台](#三用-nginx-对外暴露后台)。
**任何情况下都不要把 `WEB_HOST` 改成 `0.0.0.0` 了事**——那是明文 HTTP 直接裸奔。

### 可调的变量

```bash
sudo APP_DIR=/srv/tcw APP_USER=tcw SERVICE_NAME=tcw deploy/install.sh
```

| 变量 | 默认值 |
|---|---|
| `APP_DIR` | `/opt/tg-course-worker` |
| `APP_USER` | `tgworker` |
| `SERVICE_NAME` | `tg-course-worker` |
| `PYTHON_BIN` | 自动找 `python3.12 → 3.13 → 3.11 → python3` |

### Ubuntu 22.04 要多一步

22.04 自带的是 Python 3.10，代码用了 `StrEnum`（3.11+）跑不起来。
脚本会提示你先加 PPA：

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv
```

24.04 / 26.04 自带 3.12+，不用管这一段。

## 二、Docker

仓库根目录的 `Dockerfile` 和 `docker-compose.yml` 一直有效：

```bash
cp .env.example .env && vim .env
docker compose up -d
docker compose exec worker python scripts/bootstrap.py
docker compose logs -f
```

## 三、用 nginx 对外暴露后台

**先问一句要不要做。** bot 本身不需要 nginx（long polling 是主动往外连的），
这一章只服务一件事：**让你不用开 SSH 隧道也能打开管理后台**。
只在自己电脑上用的话，隧道更省事也更安全，这章可以跳过。

需要做的话，只有一条路：**nginx + HTTPS**。别的都不要考虑。

### 3.1 开始之前

1. 一个域名，A 记录指向这台机器，比如 `admin.example.com`
2. 防火墙放行 80 和 443：`sudo ufw allow 80,443/tcp`
3. **8080 端口绝对不要放行**——应用只绑 `127.0.0.1`，
   外面本来也连不上，放行了反而容易在将来改错配置时出事
4. `.env` 里的 `WEB_HOST` 保持 `127.0.0.1` 不动

### 3.2 装 nginx 和证书

```bash
sudo apt-get install -y nginx certbot

# 先签证书，用 webroot 方式。
# 刻意不用 --nginx 插件：它会去改写 nginx 配置，和下面这份互相打架。
# 我们这份配置的 TLS 参数是自带的，不 include certbot 的任何文件。
sudo mkdir -p /var/www/html
sudo certbot certonly --webroot -w /var/www/html -d admin.example.com --agree-tos -m 你的邮箱@example.com
```

**顺序不能反**：`--webroot` 靠 nginx 把 `/var/www/html` 挂在 80 端口上
才能完成验证，而这件事是 nginx 默认站点做的——所以必须先签证书，
再到 3.3 去删默认站点。装完 nginx 它会自动启动，一般不用手动 start。

签证书需要 80 端口能被 Let's Encrypt 从公网访问到。
`certbot` 报 challenge 失败时，先确认 DNS 已生效：`dig +short admin.example.com`。

删掉默认站点之后续期照样能跑：这份配置自己的 80 端口 server 块里
留了 `/.well-known/acme-challenge/`，指向同一个 `/var/www/html`。

### 3.3 装配置

```bash
sudo cp deploy/nginx/tg-course-worker.conf /etc/nginx/sites-available/tg-course-worker
sudo sed -i 's/admin\.example\.com/你的域名/g' /etc/nginx/sites-available/tg-course-worker
sudo ln -sf /etc/nginx/sites-available/tg-course-worker /etc/nginx/sites-enabled/

# 默认站点会抢 80 端口的默认 server，删掉
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` 必须先过再 reload。配置有错时 reload 不会生效但也不会报错，
`nginx -t` 是唯一能看到错误的地方。

`nginx -t` 报 `cannot load certificate`，说明 3.2 的证书没签成功，
回去看 certbot 的输出，别急着改这份配置。

### 3.4 证书续期

certbot 装好就带了一个 systemd timer，不用自己配 cron：

```bash
systemctl list-timers | grep certbot      # 确认 timer 在
sudo certbot renew --dry-run              # 演练一次续期
```

`--dry-run` 过了才算真的能续。**这一步别跳**——配置里开了一年 HSTS，
证书要是过期了，浏览器连"继续访问"的按钮都不会给。

### 3.5 配置里那几条不是摆设

这份配置里有四处是踩过坑才加的，改的时候别顺手删掉：

| 配置 | 为什么 |
|---|---|
| `client_max_body_size 12m` | 录入素材能传 10MB 的 PDF，nginx 默认只给 1MB，超了直接 413 |
| `proxy_read_timeout 300s` | 「重新生成」「按意见重写」是在请求里同步跑 LLM 的，一次二三十秒起，默认 60 秒会 504 |
| `limit_req zone=tcw_login` | 后台是单密码、没验证码、没失败锁定，公网暴露后这是唯一一道防爆破的闸 |
| `proxy_set_header` 四条 | 写在 `server` 层给所有 location 继承。**某个 location 里只要写了一条，继承来的其它三条就全没了**，要写就得全写 |

### 3.6 一个已知缺口：会话 cookie 没有 Secure 标记

`app/web/auth.py` 里 cookie 是这么发的：

```python
samesite="lax",
# 绑 127.0.0.1 走 http，置 secure 会让 cookie 根本发不出去
secure=False,
```

这是为隧道场景（明文 HTTP）写的。**挂上 nginx 走 HTTPS 之后，
这个 cookie 仍然没有 `Secure` 标记**，意味着浏览器愿意把它发到 http:// 上去。
上面的配置有 301 跳转和 HSTS 兜底，实际风险不大，但这是个真缺口。

要堵的话把那两行改成从配置读，暴露到公网时置 true。
**改之前先确认你不再用隧道访问**——置了 `Secure` 之后，
`http://127.0.0.1:8080` 就登不上去了（cookie 发不出去）。

另外两件事顺带说清楚：

- **没有 CSRF token。** `auth.py` 里写了理由：同源 + 无公网入口。
  暴露之后这个前提变了，但 cookie 上的 `SameSite=Lax` 会挡住跨站 POST，
  主要风险已经被覆盖。
- **就一个密码、没有用户体系。** 想再加一层网络过滤，
  `deploy/nginx/tg-course-worker.conf` 里已经写好了一段注释掉的
  `allow` / `deny`，取消注释按出口 IP 放行即可。
  家宽 IP 会变，用之前想清楚被关在门外时怎么办（SSH 隧道永远能兜底）。

### 3.7 装完自检

```bash
curl -I http://admin.example.com/           # 应当 301 到 https
curl -sI https://admin.example.com/healthz  # 应当 200
curl -sI https://admin.example.com/ | grep -i strict-transport   # HSTS 在不在
# 连打 20 次登录，后面几次应当出现 429（限流生效）
for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code} " -X POST https://admin.example.com/login; done; echo
```

最后拿浏览器开一次，确认能登录、能看见素材库。

## 为什么 bot 本身不需要域名和反向代理

bot 用的是 long polling 不是 webhook，主动往外连 `api.telegram.org`，
**不需要公网入口、域名、证书**。防火墙只要放行出站 443 就行，
入站可以一个端口都不开。

第三章那套 nginx 只为一件事存在：让管理后台不用开 SSH 隧道也能访问。
**跟 bot 收发消息毫无关系**，不装照样跑。

## unit 里那几条收权限的配置

```ini
ProtectSystem=strict
ReadWritePaths=/opt/tg-course-worker/data /opt/tg-course-worker/logs
```

整个文件系统对服务进程只读，只有 `data/` 和 `logs/` 可写。
代码目录归 `root`，服务账号只有读权限——进程改不了自己的源码。
`.env` 是 `600` 且归 `tgworker`，里面有 bot token 和 API key。
