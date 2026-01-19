#!/bin/bash
# 停止 gunicorn
pkill -f "gunicorn.*app:create_app"
echo "已停止 Web 服务"
