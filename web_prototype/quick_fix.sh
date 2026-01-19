#!/bin/bash
# 🔧 快速修复Web环境脚本

set -euo pipefail

# 颜色输出
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $*"
}

log_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $*"
}

log "🔧 开始修复Web环境..."

# 检查当前目录
if [[ ! -f "app.py" ]]; then
    log_error "请在web_prototype目录下运行此脚本"
    exit 1
fi

# 清理旧的虚拟环境
if [[ -d "venv" ]]; then
    log_warn "删除损坏的虚拟环境..."
    rm -rf venv
fi

# 重新创建虚拟环境
log "🐍 创建Python虚拟环境..."
python3 -m venv venv

# 检查激活脚本
if [[ ! -f "venv/bin/activate" ]]; then
    log_error "虚拟环境创建失败"
    exit 1
fi

# 激活虚拟环境并安装依赖
log "📦 安装Python依赖..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 创建systemd服务文件
log "⚙️ 创建系统服务..."
sudo tee /etc/systemd/system/xray-converter-web.service > /dev/null << EOF
[Unit]
Description=Xray Converter Web Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python app.py
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=xray-converter-web

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd并启动服务
log "🚀 启动Web服务..."
sudo systemctl daemon-reload
sudo systemctl enable xray-converter-web
sudo systemctl restart xray-converter-web

# 等待服务启动
sleep 3

# 检查服务状态
if sudo systemctl is-active xray-converter-web >/dev/null 2>&1; then
    log "✅ Web服务启动成功"
    echo ""
    echo "🌐 访问地址: http://$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}'):9090"
    echo "🔑 默认登录: admin / admin123"
    echo ""
    echo "📋 管理命令:"
    echo "  查看状态: sudo systemctl status xray-converter-web"
    echo "  查看日志: sudo journalctl -u xray-converter-web -f"
    echo "  重启服务: sudo systemctl restart xray-converter-web"
else
    log_error "Web服务启动失败"
    echo ""
    echo "查看错误日志: sudo journalctl -u xray-converter-web -n 20"
    exit 1
fi

log "🎉 修复完成！"