#!/bin/bash

# Xray Web管理系统简化部署脚本

set -e

echo "🚀 Xray Web管理系统部署"
echo "======================"

# 检查Python
echo "📋 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 需要Python 3.6+"
    exit 1
fi
echo "✅ Python版本: $(python3 --version)"

# 创建虚拟环境
echo "🔧 设置虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 虚拟环境创建完成"
else
    echo "✅ 虚拟环境已存在"
fi

# 安装依赖
echo "📦 安装依赖..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ 依赖安装完成"

# 创建目录
echo "📁 创建目录..."
mkdir -p ../data/services
mkdir -p uploads
mkdir -p logs
echo "✅ 目录创建完成"

# 设置权限
echo "🔐 设置权限..."
chmod +x app.py
if [ -f "../xray_converter_simple.sh" ]; then
    chmod +x "../xray_converter_simple.sh"
    echo "✅ Xray脚本权限设置完成"
fi

echo ""
echo "🎉 部署完成！"
echo "============"
echo "启动命令: python3 app.py"
echo "后台运行: nohup python3 app.py > logs/app.log 2>&1 &"
echo "访问地址: http://localhost:5000"
echo "默认账户: admin / admin123"

# 安装Docker Compose
install_docker_compose() {
    log_info "安装Docker Compose..."

    # 获取最新版本号
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)

    # 下载并安装Docker Compose
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose

    # 创建软链接
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

    log_success "Docker Compose安装完成"
}

# 检查系统要求
check_requirements() {
    log_info "检查系统要求..."

    # 检查操作系统
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        log_error "此脚本仅支持Linux系统"
        exit 1
    fi

    # 检测操作系统
    detect_os

    # 安装基础依赖
    install_basic_dependencies

    # 检查Python版本
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 安装失败"
        exit 1
    fi

    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_success "Python版本: $python_version"

    # 检查pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 安装失败"
        exit 1
    fi

    log_success "系统要求检查通过"
}

# 安装依赖
install_dependencies() {
    log_info "安装Python依赖..."
    
    # 创建虚拟环境
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
        log_success "虚拟环境创建成功"
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip
    
    # 安装依赖
    pip install -r requirements.txt
    
    log_success "Python依赖安装完成"
}

# 配置数据库
setup_database() {
    log_info "配置数据库..."
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 初始化数据库
    python3 -c "from app import init_db; init_db()"
    
    log_success "数据库配置完成"
}

# 生成SSL证书（自签名）
generate_ssl_cert() {
    log_info "生成SSL证书..."
    
    mkdir -p ssl
    
    if [[ ! -f "ssl/cert.pem" ]] || [[ ! -f "ssl/key.pem" ]]; then
        openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes \
            -subj "/C=CN/ST=State/L=City/O=Organization/CN=localhost"
        
        log_success "SSL证书生成完成"
        log_warning "使用的是自签名证书，生产环境请使用正式证书"
    else
        log_info "SSL证书已存在，跳过生成"
    fi
}

# 配置systemd服务
setup_systemd_service() {
    log_info "配置systemd服务..."
    
    local service_file="/etc/systemd/system/xray-web.service"
    local current_dir=$(pwd)
    local current_user=$(whoami)
    
    # 检查是否有sudo权限
    if ! sudo -n true 2>/dev/null; then
        log_warning "需要sudo权限来配置systemd服务"
        return 1
    fi
    
    # 创建服务文件
    sudo tee "$service_file" > /dev/null <<EOF
[Unit]
Description=Xray Web Management System
After=network.target

[Service]
Type=exec
User=$current_user
WorkingDirectory=$current_dir
Environment=PATH=$current_dir/venv/bin
Environment=FLASK_ENV=production
ExecStart=$current_dir/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    
    # 重新加载systemd
    sudo systemctl daemon-reload
    sudo systemctl enable xray-web
    
    log_success "systemd服务配置完成"
}

# Docker部署
deploy_with_docker() {
    log_info "使用Docker部署..."

    # 检查并安装Docker
    if ! command -v docker &> /dev/null; then
        log_warning "Docker 未安装，正在自动安装..."
        install_docker
    else
        log_success "Docker 已安装"
    fi

    # 检查并安装Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_warning "Docker Compose 未安装，正在自动安装..."
        install_docker_compose
    else
        log_success "Docker Compose 已安装"
    fi
    
    # 生成环境变量文件
    if [[ ! -f ".env" ]]; then
        cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=production
DB_PATH=/var/lib/xray-web/xray_web.db
SERVICE_DIR=/var/lib/xray-web/services
LOG_LEVEL=INFO
MONITOR_INTERVAL=30
DATA_RETENTION_DAYS=30
EOF
        log_success "环境变量文件创建完成"
    fi
    
    # 生成SSL证书
    generate_ssl_cert
    
    # 构建并启动容器
    docker-compose up -d --build
    
    log_success "Docker部署完成"
    log_info "应用将在几秒钟后可用"
}

# 安装系统服务
install_system_services() {
    log_info "安装系统服务..."

    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        # 安装nginx, supervisor等
        apt-get install -y nginx supervisor openssl

        # 启动服务
        systemctl start nginx
        systemctl enable nginx
        systemctl start supervisor
        systemctl enable supervisor

    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Rocky"* ]] || [[ "$OS" == *"AlmaLinux"* ]]; then
        # 安装nginx, supervisor等
        yum install -y nginx supervisor openssl

        # 启动服务
        systemctl start nginx
        systemctl enable nginx
        systemctl start supervisord
        systemctl enable supervisord

    fi

    log_success "系统服务安装完成"
}

# 传统部署
deploy_traditional() {
    log_info "使用传统方式部署..."

    # 安装系统服务
    install_system_services

    # 安装依赖
    install_dependencies

    # 配置数据库
    setup_database

    # 生成SSL证书
    generate_ssl_cert

    # 配置systemd服务
    setup_systemd_service

    log_success "传统部署完成"
}

# 启动服务
start_service() {
    log_info "启动服务..."
    
    if [[ "$DEPLOY_METHOD" == "docker" ]]; then
        docker-compose up -d
        log_success "Docker服务已启动"
    else
        if command -v systemctl &> /dev/null; then
            sudo systemctl start xray-web
            sudo systemctl status xray-web --no-pager
            log_success "systemd服务已启动"
        else
            log_info "手动启动服务..."
            source venv/bin/activate
            nohup gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app > xray_web.log 2>&1 &
            echo $! > xray_web.pid
            log_success "服务已在后台启动"
        fi
    fi
}

# 显示部署信息
show_deployment_info() {
    echo ""
    log_success "=== 部署完成 ==="
    echo ""
    echo "访问地址:"
    echo "  HTTP:  http://localhost:5000"
    echo "  HTTPS: https://localhost (如果配置了Nginx)"
    echo ""
    echo "默认登录信息:"
    echo "  用户名: admin"
    echo "  密码:   admin123"
    echo ""
    echo "重要文件位置:"
    echo "  数据库: $(pwd)/xray_web.db"
    echo "  日志:   $(pwd)/xray_web.log"
    echo "  配置:   $(pwd)/config.py"
    echo ""
    echo "管理命令:"
    if [[ "$DEPLOY_METHOD" == "docker" ]]; then
        echo "  查看日志: docker-compose logs -f"
        echo "  重启服务: docker-compose restart"
        echo "  停止服务: docker-compose down"
    else
        echo "  查看状态: sudo systemctl status xray-web"
        echo "  重启服务: sudo systemctl restart xray-web"
        echo "  停止服务: sudo systemctl stop xray-web"
        echo "  查看日志: journalctl -u xray-web -f"
    fi
    echo ""
    log_warning "请及时修改默认密码！"
}

# 主函数
main() {
    echo "选择部署方式:"
    echo "1) Docker部署 (推荐)"
    echo "2) 传统部署"
    echo ""
    read -p "请选择 (1-2): " -n 1 -r
    echo ""
    
    case $REPLY in
        1)
            DEPLOY_METHOD="docker"
            check_root
            deploy_with_docker
            ;;
        2)
            DEPLOY_METHOD="traditional"
            check_root
            check_requirements
            deploy_traditional
            ;;
        *)
            log_error "无效选择"
            exit 1
            ;;
    esac
    
    start_service
    show_deployment_info
}

# 运行主函数
main "$@"
