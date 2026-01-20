#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Xray Converter Web 管理系统一键部署脚本 ===${NC}"

# 1. 检查 Python 环境
echo -e "${YELLOW}[1/5] 检查 Python 环境...${NC}"

# 检测并尝试自动安装依赖 (Debian/Ubuntu)
if command -v apt-get &> /dev/null; then
    # 检查 python3-venv 是否安装
    if ! dpkg -s python3-venv &> /dev/null; then
        echo -e "${YELLOW}检测到缺少 python3-venv，尝试自动安装...${NC}"
        # 尝试使用 sudo，如果是 root 则直接运行
        if [ "$(id -u)" -eq 0 ]; then
             apt-get update && apt-get install -y python3-venv python3-pip
        else
             if command -v sudo &> /dev/null; then
                 sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
             else
                 echo -e "${RED}请手动运行: apt-get install -y python3-venv python3-pip${NC}"
             fi
        fi
    fi
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请先安装 Python 3。${NC}"
    echo "Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "CentOS/RHEL: sudo yum install python3"
    exit 1
fi
python3 --version

# 2. 创建虚拟环境
echo -e "${YELLOW}[2/5] 创建/重建虚拟环境...${NC}"
# 强制删除旧的 venv 以确保环境纯净
rm -rf venv

python3 -m venv venv
if [ $? -ne 0 ]; then
    echo -e "${RED}创建虚拟环境失败。${NC}"
    echo -e "${YELLOW}正在尝试安装 python3-venv...${NC}"
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3-venv
        # 重试创建
        python3 -m venv venv
        if [ $? -ne 0 ]; then
             echo -e "${RED}重试失败。请检查系统环境。${NC}"
             exit 1
        fi
    else
        exit 1
    fi
fi

# 3. 安装依赖
echo -e "${YELLOW}[3/5] 安装 Python 依赖...${NC}"
# 显式使用虚拟环境的 pip，避免 source 不生效的问题
./venv/bin/pip install --upgrade pip
./venv/bin/pip install --no-cache-dir -r web_prototype/requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}依赖安装失败。${NC}"
    exit 1
fi

# 4. 检查 Xray 核心
echo -e "${YELLOW}[4/5] 检查 Xray 核心...${NC}"
if [ ! -f "xray" ]; then
    echo "未找到 xray 可执行文件，尝试下载..."
    # 检测架构
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            XRAY_ARCH="64"
            ;;
        aarch64)
            XRAY_ARCH="arm64-v8a"
            ;;
        *)
            echo -e "${RED}不支持的架构: $ARCH，请手动下载 xray。${NC}"
            ;;
    esac

    if [ -n "$XRAY_ARCH" ]; then
        # 这里使用一个通用的下载逻辑，或者提示用户
        # 由于 xray 官方发布地址可能变化，这里简化处理，如果 install_native.sh 存在则使用它
        if [ -f "install_native.sh" ]; then
            echo "运行原生安装脚本..."
            bash install_native.sh
        else
            echo -e "${YELLOW}请手动下载 xray 核心并放置在项目根目录，或者运行 install_native.sh (如果存在)${NC}"
            # 尝试下载 install_native.sh 如果不存在? 不，假设 git clone 下来是完整的
        fi
    fi
else
    chmod +x xray
    echo "Xray 核心已就绪。"
fi

# 5. 初始化配置和数据库
echo -e "${YELLOW}[5/5] 初始化系统...${NC}"
# 创建必要的目录
mkdir -p data/services
mkdir -p web_prototype/instance
mkdir -p web_prototype/uploads

# 赋予脚本执行权限
chmod +x start.sh
chmod +x stop.sh 2>/dev/null || true

echo -e "${GREEN}=== 部署完成! ===${NC}"
echo -e "使用以下命令启动服务:"
echo -e "  ${GREEN}./start.sh${NC}"
echo -e "默认端口: 5000"
