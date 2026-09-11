#!/usr/bin/env bash
# 在 Ubuntu 上把 tg-course-worker 装成 systemd 服务。
#
#   sudo deploy/install.sh
#
# 重复跑是安全的：升级代码后再跑一次就是一次滚动更新。
# .env、data/、logs/ 都不会被覆盖。
set -euo pipefail

APP_USER="${APP_USER:-tgworker}"
APP_DIR="${APP_DIR:-/opt/tg-course-worker}"
SERVICE_NAME="${SERVICE_NAME:-tg-course-worker}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$SRC_DIR/deploy/$SERVICE_NAME.service"
UNIT_DST="/etc/systemd/system/$SERVICE_NAME.service"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "要用 root 跑：sudo deploy/install.sh"
[ -f "$SRC_DIR/requirements.txt" ] || die "在 $SRC_DIR 下找不到 requirements.txt，这不是项目根目录"
[ -f "$UNIT_SRC" ] || die "找不到 unit 模板 $UNIT_SRC"

# ---------------------------------------------------------------- 系统依赖
say "安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# libxml2/libxslt 是 trafilatura(lxml) 的运行时依赖；
# pymupdf 带自己的二进制，不需要额外的库
apt-get install -y -qq --no-install-recommends \
    ca-certificates tzdata sqlite3 rsync libxml2 libxslt1.1 >/dev/null

# ---------------------------------------------------------------- Python
# 需要 3.11+（代码用了 StrEnum）。Ubuntu 24.04+ 自带 3.12；
# 22.04 只有 3.10，得从 deadsnakes 装。
pick_python() {
    local c v
    for c in python3.12 python3.13 python3.11 python3; do
        command -v "$c" >/dev/null 2>&1 || continue
        v="$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)"
        if [ "$v" -ge 311 ]; then echo "$c"; return 0; fi
    done
    return 1
}

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(pick_python || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
    say "系统里没有 3.11+ 的 Python，尝试安装 python3.12"
    apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv >/dev/null 2>&1 || true
    PYTHON_BIN="$(pick_python || true)"
fi
[ -n "$PYTHON_BIN" ] || die "装不上 Python 3.11+。Ubuntu 22.04 请先执行：
  sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get update
  sudo apt-get install -y python3.12 python3.12-venv
然后重新运行本脚本。"

PY_VER="$("$PYTHON_BIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
say "使用 $PYTHON_BIN（$PY_VER）"
# venv 模块在 Ubuntu 上是单独的包，缺了 python -m venv 会失败得很难懂
"$PYTHON_BIN" -c 'import venv' 2>/dev/null \
    || apt-get install -y -qq --no-install-recommends "python$PY_VER-venv" >/dev/null

# ---------------------------------------------------------------- 用户
if id "$APP_USER" >/dev/null 2>&1; then
    say "服务账号 $APP_USER 已存在"
else
    say "创建服务账号 $APP_USER"
    # 系统账号：不能登录、没有家目录。被拿下也登不进来。
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# ---------------------------------------------------------------- 同步代码
say "同步代码到 $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" = "$APP_DIR" ]; then
    say "  源码已经就在 $APP_DIR，跳过同步"
else
    # --delete 只作用在下面列出的代码目录，不会碰 data/ logs/ .env
    rsync -a --delete \
        --exclude='__pycache__/' --exclude='*.py[cod]' \
        "$SRC_DIR/app/" "$APP_DIR/app/"
    rsync -a --delete \
        --exclude='__pycache__/' --exclude='*.py[cod]' \
        "$SRC_DIR/config/" "$APP_DIR/config/"
    rsync -a --delete \
        --exclude='__pycache__/' --exclude='*.py[cod]' \
        "$SRC_DIR/scripts/" "$APP_DIR/scripts/"
    rsync -a "$SRC_DIR/deploy/" "$APP_DIR/deploy/"
    for f in requirements.txt .env.example README.md CLAUDE.md; do
        # 末尾的 || true 不能省：某个文件不存在时 [ -f ] 返回 1，
        # 循环退出码就是 1，set -e 会把整个脚本干掉
        [ -f "$SRC_DIR/$f" ] && cp -f "$SRC_DIR/$f" "$APP_DIR/$f" || true
    done
fi
mkdir -p "$APP_DIR/data/media" "$APP_DIR/logs"

# ---------------------------------------------------------------- venv
say "准备虚拟环境"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -q -r "$APP_DIR/requirements.txt"

# ---------------------------------------------------------------- .env
FIRST_RUN=0
if [ ! -f "$APP_DIR/.env" ]; then
    FIRST_RUN=1
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    warn "已生成 $APP_DIR/.env（内容是示例值，服务暂不启动）"
fi

# ---------------------------------------------------------------- 权限
say "设置权限"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/data" "$APP_DIR/logs"
# 代码归 root，服务账号只读：进程改不了自己的源码
chown -R root:root "$APP_DIR/app" "$APP_DIR/config" "$APP_DIR/scripts"
# .env 里有 bot token 和 API key，只给服务账号读
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
# data/ 里是数据库，别让同机其他用户翻
chmod 750 "$APP_DIR/data" "$APP_DIR/logs"

# ---------------------------------------------------------------- systemd
say "安装 systemd unit"
sed -e "s|@APP_DIR@|$APP_DIR|g" \
    -e "s|@APP_USER@|$APP_USER|g" \
    -e "s|@SERVICE_NAME@|$SERVICE_NAME|g" \
    "$UNIT_SRC" > "$UNIT_DST"
chmod 644 "$UNIT_DST"
systemctl daemon-reload
systemctl enable -q "$SERVICE_NAME"

# restart.sh 放一份到 /usr/local/bin，随处可调
install -m 755 "$SRC_DIR/deploy/restart.sh" "/usr/local/bin/$SERVICE_NAME-restart"

echo
if [ "$FIRST_RUN" -eq 1 ]; then
    say "安装完成。接下来还差三步："
    cat <<TIP

  1) 填配置（OWNER_ID、bot token、DEEPSEEK_API_KEY、WEB_PASSWORD 等）
       sudo -e $APP_DIR/.env

  2) 建第一套 bot / 内容方向 / 频道
       sudo -u $APP_USER $APP_DIR/.venv/bin/python $APP_DIR/scripts/bootstrap.py

  3) 启动
       sudo systemctl start $SERVICE_NAME

  之后看日志：  journalctl -u $SERVICE_NAME -f
  访问后台：    ssh -L 8080:127.0.0.1:8080 <你>@<这台机器>  然后开 http://127.0.0.1:8080
TIP
elif systemctl is-active --quiet "$SERVICE_NAME"; then
    say "代码已更新，重启服务"
    systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        say "服务运行中。日志：journalctl -u $SERVICE_NAME -f"
    else
        die "服务没起来，看日志：journalctl -u $SERVICE_NAME -n 50 --no-pager"
    fi
else
    # 装过但没启动过：多半是 .env 还没填完。
    # 这种情况下 restart 只会失败得莫名其妙，不如直接把下一步告诉人。
    say "代码已更新。服务当前没在运行，填好 $APP_DIR/.env 后启动："
    echo "    sudo systemctl start $SERVICE_NAME"
fi
