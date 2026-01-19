#!/bin/bash
# 快速启动脚本 - 服务器部署后的快速验证工具

set -euo pipefail

# 颜色定义
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 日志函数
log() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# 检查脚本是否在正确目录运行
check_directory() {
    if [ ! -f "xray_converter_simple.sh" ]; then
        log_error "请在项目根目录运行此脚本"
        exit 1
    fi
}

# 检查系统环境
check_environment() {
    log "检查系统环境..."
    
    # 检查操作系统
    local os=$(uname -s)
    local arch=$(uname -m)
    log "操作系统: $os $arch"
    
    # 检查必要命令
    local missing_deps=()
    for cmd in curl wget unzip; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_warning "缺少依赖: ${missing_deps[*]}"
        echo "请安装缺少的依赖："
        echo "Ubuntu/Debian: sudo apt update && sudo apt install ${missing_deps[*]}"
        echo "CentOS/RHEL: sudo yum install ${missing_deps[*]}"
        return 1
    else
        log_success "系统依赖检查通过"
    fi
    
    # 检查Python
    if command -v python3 >/dev/null 2>&1; then
        local python_version=$(python3 --version)
        log_success "Python: $python_version"
    else
        log_warning "Python3 未安装，Web界面功能不可用"
    fi
}

# 设置权限
setup_permissions() {
    log "设置文件权限..."
    
    # 设置脚本执行权限
    chmod +x *.sh *.py 2>/dev/null || true
    
    # 检查权限设置
    local executable_files=0
    for file in *.sh *.py; do
        if [ -x "$file" ]; then
            executable_files=$((executable_files + 1))
        fi
    done
    
    log_success "已设置 $executable_files 个文件的执行权限"
}

# 测试核心功能
test_core_functions() {
    log "测试核心功能..."
    
    # 测试Xray二进制
    if [ -f "xray" ]; then
        if [ -x "xray" ]; then
            local xray_version=$(./xray version 2>/dev/null | head -1 || echo "无法获取版本")
            log_success "Xray: $xray_version"
        else
            log_warning "Xray文件存在但不可执行"
            chmod +x xray
        fi
    else
        log_warning "Xray二进制文件不存在，将在首次运行时下载"
    fi
    
    # 测试脚本语法
    echo -n "检查主脚本语法... "
    if bash -n xray_converter_simple.sh; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        return 1
    fi
    
    echo -n "检查诊断工具语法... "
    if bash -n xray_diagnostics.sh; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        return 1
    fi
    
    echo -n "检查监控工具语法... "
    if bash -n xray_monitor.sh; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        return 1
    fi
    
    # 测试Python脚本
    if command -v python3 >/dev/null 2>&1; then
        echo -n "检查SS链接工具... "
        if python3 -m py_compile ss_link_utils.py 2>/dev/null; then
            echo -e "${GREEN}✅${NC}"
        else
            echo -e "${RED}❌${NC}"
            return 1
        fi
    fi
}

# 网络环境检查
check_network() {
    log "检查网络环境..."
    
    # 检查端口可用性
    local test_ports=(10000 20000 30000)
    local available_ports=0
    
    for port in "${test_ports[@]}"; do
        if ! netstat -tln 2>/dev/null | grep ":$port " >/dev/null; then
            available_ports=$((available_ports + 1))
        fi
    done
    
    log_success "$available_ports/${#test_ports[@]} 测试端口可用"
    
    # 检查防火墙状态
    if command -v ufw >/dev/null 2>&1; then
        local ufw_status=$(sudo ufw status 2>/dev/null | head -1 || echo "无法检查")
        log "防火墙状态 (ufw): $ufw_status"
    elif command -v firewall-cmd >/dev/null 2>&1; then
        local firewall_status=$(sudo firewall-cmd --state 2>/dev/null || echo "无法检查")
        log "防火墙状态 (firewalld): $firewall_status"
    else
        log_warning "未检测到常见的防火墙工具"
    fi
}

# 系统资源检查
check_resources() {
    log "检查系统资源..."
    
    # 内存检查
    if [ -f /proc/meminfo ]; then
        local mem_total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        local mem_total_mb=$((mem_total_kb / 1024))
        local mem_available_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}' || echo "$mem_total_kb")
        local mem_available_mb=$((mem_available_kb / 1024))
        
        log "内存: ${mem_available_mb}MB 可用 / ${mem_total_mb}MB 总计"
        
        if [ $mem_available_mb -lt 256 ]; then
            log_warning "可用内存较少，建议至少256MB"
        else
            log_success "内存充足"
        fi
    fi
    
    # 磁盘空间检查
    local disk_usage=$(df -h . | tail -1 | awk '{print $4}')
    log "磁盘可用空间: $disk_usage"
    
    # CPU核心数
    local cpu_cores=$(nproc 2>/dev/null || echo "未知")
    log "CPU核心数: $cpu_cores"
}

# 运行快速测试
run_quick_test() {
    log "运行快速功能测试..."
    
    # 测试诊断工具
    echo -n "测试系统诊断... "
    if ./xray_diagnostics.sh system >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️${NC}"
    fi
    
    # 测试监控工具
    echo -n "测试监控状态... "
    if ./xray_monitor.sh status >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️${NC}"
    fi
    
    # 测试SS链接工具
    if command -v python3 >/dev/null 2>&1; then
        echo -n "测试SS链接工具... "
        if ./ss_link_utils.py --help >/dev/null 2>&1; then
            echo -e "${GREEN}✅${NC}"
        else
            echo -e "${YELLOW}⚠️${NC}"
        fi
    fi
}

# 显示启动建议
show_recommendations() {
    echo ""
    echo "========================================"
    echo "  🚀 快速启动建议"
    echo "========================================"
    echo ""
    echo "1. 启动主程序："
    echo "   ./xray_converter_simple.sh"
    echo ""
    echo "2. 或使用安装脚本："
    echo "   ./install_native.sh"
    echo ""
    echo "3. 启动监控服务："
    echo "   ./xray_monitor.sh start --daemon"
    echo ""
    echo "4. Web界面 (可选)："
    echo "   cd web_prototype"
    echo "   pip3 install -r requirements.txt"
    echo "   python3 app.py"
    echo ""
    echo "5. 查看帮助："
    echo "   ./xray_diagnostics.sh help"
    echo "   ./xray_monitor.sh help"
    echo "   ./ss_link_utils.py --help"
    echo ""
    echo "📖 详细部署指南请查看: DEPLOYMENT_GUIDE.md"
    echo ""
}

# 主函数
main() {
    clear
    echo "========================================"
    echo "  Xray转换器 - 快速启动检查"
    echo "========================================"
    echo ""
    
    check_directory
    
    local all_passed=true
    
    # 执行各项检查
    if ! check_environment; then
        all_passed=false
    fi
    
    setup_permissions
    
    if ! test_core_functions; then
        all_passed=false
    fi
    
    check_network
    check_resources
    run_quick_test
    
    echo ""
    echo "========================================"
    if [ "$all_passed" = true ]; then
        echo -e "  ${GREEN}✅ 快速检查完成 - 一切正常！${NC}"
    else
        echo -e "  ${YELLOW}⚠️ 快速检查完成 - 发现一些问题${NC}"
        echo -e "  ${YELLOW}   请检查上面的警告信息${NC}"
    fi
    echo "========================================"
    
    show_recommendations
}

main "$@"