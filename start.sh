#!/bin/bash

# 获取脚本所在目录的绝对路径
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "未找到虚拟环境，请先运行 ./deploy.sh"
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
# --access-logfile: 访问日志
# --error-logfile: 错误日志
# --daemon: 后台运行 (可选，这里默认前台运行以便调试，生产环境可加 --daemon)

exec gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()" \
    --access-logfile ../access.log \
    --error-logfile ../error.log
