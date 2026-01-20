#!/bin/bash

# 获取脚本所在目录的绝对路径
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 激活虚拟环境 (可选，主要用于环境变量)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 检查 gunicorn 是否存在于 venv 中
if [ -f "./venv/bin/gunicorn" ]; then
    GUNICORN="./venv/bin/gunicorn"
else
    echo -e "\033[0;31m错误: 在虚拟环境中未找到 gunicorn。\033[0m"
    echo "请重新运行 ./deploy.sh 修复安装。"
    exit 1
fi

# 设置环境变量
export PYTHONPATH=$DIR

# 启动服务
echo "正在启动 Xray Web Converter..."
echo "访问地址: http://0.0.0.0:5000"

cd web_prototype
# 使用 gunicorn 启动
# -w 4: 4个工作进程
# -b: 绑定地址
# --daemon: 后台运行
# --access-logfile: 访问日志
# --error-logfile: 错误日志

$GUNICORN -w 4 -b 0.0.0.0:5000 "app:create_app()" \
    --daemon \
    --access-logfile ../access.log \
    --error-logfile ../error.log

echo "服务已在后台启动。"
echo "查看日志: tail -f access.log"
