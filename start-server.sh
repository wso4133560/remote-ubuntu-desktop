#!/bin/bash

# 服务器启动脚本

# 切换到项目根目录
cd "$(dirname "$0")"

echo "Starting Remote Control Server..."

# 检查是否已安装依赖
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 设置 PYTHONPATH 并启动服务器
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
