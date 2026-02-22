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

SERVER_HOST="${RC_SERVER_HOST:-0.0.0.0}"
SERVER_PORT="${RC_SERVER_PORT:-8000}"

if [ "${RC_SERVER_RELOAD:-0}" = "1" ]; then
    echo "Dev reload enabled (RC_SERVER_RELOAD=1)"
    uvicorn server.main:app \
        --host "${SERVER_HOST}" \
        --port "${SERVER_PORT}" \
        --reload \
        --reload-include "*.py" \
        --reload-exclude "remote_control.db"
else
    uvicorn server.main:app \
        --host "${SERVER_HOST}" \
        --port "${SERVER_PORT}"
fi
