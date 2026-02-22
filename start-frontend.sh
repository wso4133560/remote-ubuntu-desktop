#!/bin/bash

# 前端启动脚本

cd "$(dirname "$0")/frontend"

echo "Starting Remote Control Frontend..."

# 检查是否已安装依赖
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# 启动开发服务器
npm run dev
