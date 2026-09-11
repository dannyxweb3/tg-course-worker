#!/bin/sh
# 重启服务。改完 .env 或 config/prompts/ 之后跑这个。
# 看日志：journalctl -u tg-course-worker -f
S="${SERVICE_NAME:-tg-course-worker}"; [ "$(id -u)" = 0 ] && exec systemctl restart "$S" || exec sudo systemctl restart "$S"
