#!/bin/bash

# 获取脚本所在目录的绝对路径
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 激活虚拟环境 (可选，主要用于环境变量)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 定义 Python 解释器路径 (使用绝对路径避免歧义)
PYTHON="$DIR/venv/bin/python3"

# 检查虚拟环境 Python
if [ ! -f "$PYTHON" ]; then
    echo -e "\033[0;31m错误: 未找到虚拟环境 Python 解释器 ($PYTHON)。\033[0m"
    echo "请重新运行 ./deploy.sh 修复安装。"
    exit 1
fi

# 检查 gunicorn 模块是否安装
$PYTHON -m gunicorn --version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "\033[0;31m错误: gunicorn 未正确安装。\033[0m"
    echo "请重新运行 ./deploy.sh 修复安装。"
    exit 1
fi

# 设置环境变量
export PYTHONPATH=$DIR

# 启动服务
echo "正在启动 Xray Web Converter..."
echo "访问地址: http://0.0.0.0:5000"

cd web_prototype
# 使用 python -m gunicorn 启动，避免 shebang 问题
$PYTHON -m gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()" \
    --daemon \
    --access-logfile ../access.log \
    --error-logfile ../error.log

if [ $? -eq 0 ]; then
    echo "服务已在后台启动。"
    echo "查看日志: tail -f access.log"
else
    echo -e "\033[0;31m启动失败: gunicorn 进程无法启动\033[0m"
    if [ -f "../error.log" ]; then
        echo "错误日志 (最后10行):"
        tail -n 10 ../error.log
    fi
    exit 1
fi
