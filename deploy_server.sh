#!/bin/bash
# 服务器部署脚本

set -euo pipefail

# 配置
readonly DEPLOY_USER="${DEPLOY_USER:-root}"
readonly DEPLOY_HOST="${DEPLOY_HOST:-your-server.com}"
readonly DEPLOY_PATH="${DEPLOY_PATH:-/opt/xray-converter}"
readonly SERVICE_PORT="${SERVICE_PORT:-9090}"

# 颜色输出
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $*"
}

log_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $*" >&2
}

# 检查依赖
check_dependencies() {
    log "检查本地依赖..."
    
    if ! command -v git >/dev/null 2>&1; then
        log_error "Git 未安装"
        exit 1
    fi
    
    if ! command -v ssh >/dev/null 2>&1; then
        log_error "SSH 未安装"
        exit 1
    fi
    
    log "✅ 本地依赖检查完成"
}

# 部署到服务器
deploy_to_server() {
    log "开始部署到服务器..."
    
    # 创建部署目录
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_PATH}"
    
    # 上传文件（排除敏感数据）
    log "上传项目文件..."
    rsync -avz --progress \
        --exclude='.git' \
        --exclude='data/services/*/config.json' \
        --exclude='data/services/*/info.txt' \
        --exclude='data/services/*/*.pid' \
        --exclude='data/services/*/*.log' \
        --exclude='web_prototype/venv' \
        --exclude='web_prototype/*.db' \
        --exclude='web_prototype/*.log' \
        --exclude='__pycache__' \
        --exclude='.DS_Store' \
        ./ "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
    
    # 服务器端设置
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${DEPLOY_PATH} && bash -s" << 'EOF'
        # 安装系统依赖
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update
            apt-get install -y python3 python3-pip python3-venv curl unzip
        elif command -v yum >/dev/null 2>&1; then
            yum install -y python3 python3-pip curl unzip
        fi
        
        # 设置Python虚拟环境
        cd web_prototype
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        
        # 设置文件权限
        cd ..
        chmod +x *.sh
        chmod +x web_prototype/*.sh
        
        # 创建系统服务
        cat > /etc/systemd/system/xray-converter-web.service << 'SYSTEMD'
[Unit]
Description=Xray Converter Web Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=DEPLOY_PATH/web_prototype
Environment=PATH=DEPLOY_PATH/web_prototype/venv/bin
ExecStart=DEPLOY_PATH/web_prototype/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD
        
        # 替换路径
        sed -i "s|DEPLOY_PATH|${DEPLOY_PATH}|g" /etc/systemd/system/xray-converter-web.service
        
        # 启用和启动服务
        systemctl daemon-reload
        systemctl enable xray-converter-web
        systemctl restart xray-converter-web
        
        echo "🎉 部署完成！"
        echo "Web界面地址: http://$(hostname -I | awk '{print $1}'):SERVICE_PORT"
        echo "默认登录: admin / admin123"
EOF
    
    log "✅ 部署完成！"
}

# 主函数
main() {
    echo "======================================"
    echo "    Xray转换器 - 服务器部署工具"
    echo "======================================"
    echo ""
    
    if [[ $# -eq 0 ]]; then
        echo "使用方法:"
        echo "  $0 deploy                    # 部署到服务器"
        echo "  $0 status                    # 检查服务状态"
        echo "  $0 logs                      # 查看服务日志"
        echo ""
        echo "环境变量:"
        echo "  DEPLOY_USER=用户名           # 服务器用户名 (默认: root)"
        echo "  DEPLOY_HOST=服务器地址       # 服务器IP或域名"
        echo "  DEPLOY_PATH=部署路径         # 部署目录 (默认: /opt/xray-converter)"
        echo "  SERVICE_PORT=端口            # Web服务端口 (默认: 9090)"
        echo ""
        echo "示例:"
        echo "  DEPLOY_HOST=1.2.3.4 $0 deploy"
        exit 1
    fi
    
    case "$1" in
        deploy)
            if [[ -z "${DEPLOY_HOST:-}" ]]; then
                log_error "请设置 DEPLOY_HOST 环境变量"
                echo "示例: DEPLOY_HOST=1.2.3.4 $0 deploy"
                exit 1
            fi
            check_dependencies
            deploy_to_server
            ;;
        status)
            ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "systemctl status xray-converter-web"
            ;;
        logs)
            ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "journalctl -u xray-converter-web -f"
            ;;
        *)
            log_error "未知命令: $1"
            exit 1
            ;;
    esac
}

main "$@"