#!/bin/bash
# 🚀 Xray转换器 - GitHub一键部署脚本

set -euo pipefail

# 颜色输出
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly NC='\033[0m'

# 配置
GITHUB_REPO="${GITHUB_REPO:-}"
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/xray-converter}"
SERVICE_PORT="${SERVICE_PORT:-9090}"

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $*"
}

log_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $*" >&2
}

log_info() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"
}

show_banner() {
    echo -e "${PURPLE}"
    cat << 'EOF'
  ╔══════════════════════════════════════════════════════════════════╗
  ║                   🚀 Xray转换器 一键部署工具                      ║
  ║                                                                  ║
  ║  🌐 GitHub自动化部署 + 服务器配置 + Web界面                       ║
  ╚══════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# 检查依赖
check_dependencies() {
    log "检查本地依赖..."
    
    local deps=("git" "ssh" "curl")
    local missing_deps=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            missing_deps+=("$dep")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "缺少依赖: ${missing_deps[*]}"
        echo ""
        echo "请安装缺少的依赖："
        echo "  macOS: brew install ${missing_deps[*]}"
        echo "  Ubuntu/Debian: sudo apt install ${missing_deps[*]}"
        echo "  CentOS/RHEL: sudo yum install ${missing_deps[*]}"
        exit 1
    fi
    
    log "✅ 依赖检查完成"
}

# 获取用户输入
get_user_input() {
    echo ""
    log_info "🔧 配置部署参数"
    echo ""
    
    # GitHub仓库
    if [[ -z "${GITHUB_REPO}" ]]; then
        read -p "$(echo -e ${BLUE}请输入GitHub仓库地址 (如: username/xray-converter): ${NC})" GITHUB_REPO
        if [[ -z "${GITHUB_REPO}" ]]; then
            log_error "GitHub仓库地址不能为空"
            exit 1
        fi
    fi
    
    # 服务器地址
    if [[ -z "${DEPLOY_HOST}" ]]; then
        read -p "$(echo -e ${BLUE}请输入服务器IP或域名: ${NC})" DEPLOY_HOST
        if [[ -z "${DEPLOY_HOST}" ]]; then
            log_error "服务器地址不能为空"
            exit 1
        fi
    fi
    
    # 可选参数
    echo ""
    echo -e "${YELLOW}可选配置 (直接回车使用默认值):${NC}"
    
    read -p "部署用户 [${DEPLOY_USER}]: " input_user
    DEPLOY_USER="${input_user:-$DEPLOY_USER}"
    
    read -p "部署路径 [${DEPLOY_PATH}]: " input_path
    DEPLOY_PATH="${input_path:-$DEPLOY_PATH}"
    
    read -p "服务端口 [${SERVICE_PORT}]: " input_port
    SERVICE_PORT="${input_port:-$SERVICE_PORT}"
    
    echo ""
    log_info "📋 部署配置确认:"
    echo "  GitHub仓库: ${GITHUB_REPO}"
    echo "  服务器地址: ${DEPLOY_HOST}"
    echo "  部署用户: ${DEPLOY_USER}"
    echo "  部署路径: ${DEPLOY_PATH}"
    echo "  服务端口: ${SERVICE_PORT}"
    echo ""
    
    read -p "$(echo -e ${YELLOW}确认开始部署? [y/N]: ${NC})" confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_warn "部署已取消"
        exit 0
    fi
}

# 测试SSH连接
test_ssh_connection() {
    log "🔗 测试SSH连接到 ${DEPLOY_USER}@${DEPLOY_HOST}..."
    
    if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${DEPLOY_USER}@${DEPLOY_HOST}" "echo 'SSH连接成功'" >/dev/null 2>&1; then
        log "✅ SSH连接测试成功"
    else
        log_error "❌ SSH连接失败"
        echo ""
        echo "请确保:"
        echo "1. 服务器地址正确"
        echo "2. SSH密钥已配置或可以密码登录"
        echo "3. 服务器SSH服务正在运行"
        echo ""
        echo "测试命令: ssh ${DEPLOY_USER}@${DEPLOY_HOST}"
        exit 1
    fi
}

# 推送到GitHub (如果是本地项目)
push_to_github() {
    if [[ -d ".git" ]]; then
        log "📤 推送代码到GitHub..."
        
        # 检查是否有远程仓库
        if ! git remote get-url origin >/dev/null 2>&1; then
            git remote add origin "https://github.com/${GITHUB_REPO}.git"
        fi
        
        # 推送代码
        if git push -u origin main 2>/dev/null; then
            log "✅ 代码推送成功"
        else
            log_warn "代码推送失败，可能需要手动推送"
        fi
    else
        log_info "当前目录不是Git仓库，跳过代码推送"
    fi
}

# 直接部署到服务器
deploy_to_server() {
    log "🚀 开始部署到服务器..."
    
    # 创建临时目录
    local temp_dir="/tmp/xray-converter-deploy-$$"
    
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "
        set -euo pipefail
        
        echo '📦 准备部署环境...'
        mkdir -p ${temp_dir}
        cd ${temp_dir}
        
        echo '📥 克隆代码...'
        if command -v git >/dev/null 2>&1; then
            git clone https://github.com/${GITHUB_REPO}.git .
        else
            echo '安装Git...'
            if command -v apt-get >/dev/null 2>&1; then
                apt-get update && apt-get install -y git
            elif command -v yum >/dev/null 2>&1; then
                yum install -y git
            fi
            git clone https://github.com/${GITHUB_REPO}.git .
        fi
        
        echo '📁 创建部署目录...'
        mkdir -p ${DEPLOY_PATH}
        
        echo '📋 复制文件...'
        rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.log' --exclude='*.pid' ./ ${DEPLOY_PATH}/
        
        cd ${DEPLOY_PATH}
        
        echo '📦 安装系统依赖...'
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update
            apt-get install -y python3 python3-pip python3-venv curl unzip nginx
        elif command -v yum >/dev/null 2>&1; then
            yum update -y
            yum install -y python3 python3-pip curl unzip nginx
        fi
        
        echo '🐍 设置Python环境...'
        cd web_prototype
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        
        echo '📝 设置权限...'
        cd ..
        chmod +x *.sh
        find . -name \"*.sh\" -exec chmod +x {} \;
        
        echo '🔧 创建系统服务...'
        cat > /etc/systemd/system/xray-converter-web.service << 'EOF'
[Unit]
Description=Xray Converter Web Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${DEPLOY_PATH}/web_prototype
Environment=PATH=${DEPLOY_PATH}/web_prototype/venv/bin
ExecStart=${DEPLOY_PATH}/web_prototype/venv/bin/python app.py
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=xray-converter-web

[Install]
WantedBy=multi-user.target
EOF
        
        echo '🌐 配置Nginx...'
        cat > /etc/nginx/sites-available/xray-converter << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:${SERVICE_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
    }
}
EOF
        
        ln -sf /etc/nginx/sites-available/xray-converter /etc/nginx/sites-enabled/
        rm -f /etc/nginx/sites-enabled/default
        
        echo '🚀 启动服务...'
        systemctl daemon-reload
        systemctl enable xray-converter-web
        systemctl restart xray-converter-web
        
        nginx -t && systemctl enable nginx && systemctl restart nginx
        
        echo '🧹 清理临时文件...'
        rm -rf ${temp_dir}
        
        echo '✅ 部署完成!'
    "
}

# 验证部署
verify_deployment() {
    log "🧪 验证部署结果..."
    
    # 等待服务启动
    sleep 10
    
    # 检查服务状态
    if ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "systemctl is-active xray-converter-web >/dev/null 2>&1"; then
        log "✅ Web服务运行正常"
    else
        log_error "❌ Web服务启动失败"
        echo ""
        echo "查看服务日志:"
        echo "  ssh ${DEPLOY_USER}@${DEPLOY_HOST} 'journalctl -u xray-converter-web -n 20'"
        return 1
    fi
    
    # 测试HTTP访问
    if curl -f -s -o /dev/null -m 10 "http://${DEPLOY_HOST}" 2>/dev/null; then
        log "✅ Web界面访问正常"
    else
        log_warn "⚠️  Web界面可能需要几分钟才能完全启动"
    fi
}

# 显示结果
show_results() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                        🎉 部署成功!                               ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}📋 访问信息:${NC}"
    echo "  🌐 Web界面: http://${DEPLOY_HOST}"
    echo "  🔑 默认登录: admin / admin123"
    echo "  📁 部署路径: ${DEPLOY_PATH}"
    echo ""
    echo -e "${BLUE}🔧 管理命令:${NC}"
    echo "  查看状态: ssh ${DEPLOY_USER}@${DEPLOY_HOST} 'systemctl status xray-converter-web'"
    echo "  查看日志: ssh ${DEPLOY_USER}@${DEPLOY_HOST} 'journalctl -u xray-converter-web -f'"
    echo "  重启服务: ssh ${DEPLOY_USER}@${DEPLOY_HOST} 'systemctl restart xray-converter-web'"
    echo ""
    echo -e "${BLUE}📖 文档:${NC}"
    echo "  项目仓库: https://github.com/${GITHUB_REPO}"
    echo "  使用指南: ${DEPLOY_PATH}/USAGE.md"
    echo ""
}

# 主函数
main() {
    show_banner
    
    # 检查参数
    if [[ $# -gt 0 ]] && [[ "$1" == "--help" || "$1" == "-h" ]]; then
        echo "使用方法:"
        echo "  $0                          # 交互式部署"
        echo "  GITHUB_REPO=user/repo DEPLOY_HOST=1.2.3.4 $0  # 环境变量部署"
        echo ""
        echo "环境变量:"
        echo "  GITHUB_REPO=用户名/仓库名    # GitHub仓库"
        echo "  DEPLOY_HOST=服务器地址       # 服务器IP或域名"
        echo "  DEPLOY_USER=用户名           # SSH用户名 (默认: root)"
        echo "  DEPLOY_PATH=部署路径         # 部署目录 (默认: /opt/xray-converter)"
        echo "  SERVICE_PORT=端口            # Web端口 (默认: 9090)"
        exit 0
    fi
    
    check_dependencies
    get_user_input
    test_ssh_connection
    push_to_github
    deploy_to_server
    
    if verify_deployment; then
        show_results
    else
        log_error "部署验证失败，请检查服务状态"
        exit 1
    fi
}

main "$@"