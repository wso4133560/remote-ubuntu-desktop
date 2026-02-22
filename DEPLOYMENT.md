# 部署指南

## 系统要求

### 服务器
- Ubuntu 20.04/22.04/24.04 LTS
- Python 3.11+
- 2GB RAM
- 10GB 磁盘空间

### 客户端（被控端）
- Ubuntu 20.04/22.04/24.04 LTS
- Wayland 桌面环境（GNOME 或 wlroots）
- Python 3.11+
- 1GB RAM

### 操作端
- Chrome 或 Edge 浏览器（最新版本）
- 稳定的网络连接

## 快速部署

### 1. 服务器部署

```bash
# 克隆项目
cd /opt
git clone <repository-url> remote-control
cd remote-control

# 安装依赖
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 启动服务器（必须从项目根目录启动）
cd /opt/remote-control
source server/venv/bin/activate
uvicorn server.main:app --host 0.0.0.0 --port 8000

# 或使用启动脚本
./start-server.sh
```

### 2. 初始化系统并创建管理员账户

系统首次启动时没有默认账户，需要手动创建管理员账户：

```bash
# 检查初始化状态
curl http://localhost:8000/api/v1/setup/status

# 创建管理员账户（自定义用户名和密码）
curl -X POST http://localhost:8000/api/v1/setup/initialize \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_secure_password"}'
```

**账户要求**：
- 用户名：3-64 个字符
- 密码：最少 8 个字符
- 系统只允许初始化一次

**快速测试账户示例**：
```bash
curl -X POST http://localhost:8000/api/v1/setup/initialize \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123456"}'
```

创建成功后，使用该账户登录 Web 前端。

### 3. 部署 Web 前端

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build
# 构建产物在 dist/ 目录
```

### 4. 部署客户端

```bash
cd client

# 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 创建配置文件
sudo mkdir -p /etc/remote-control
sudo cp config.example.json /etc/remote-control/client.conf

# 编辑配置
sudo nano /etc/remote-control/client.conf
# 修改 server_url 和 device_name

# 运行客户端
python -m client.main /etc/remote-control/client.conf
```

## 生产环境部署

### 使用 systemd 管理服务器

创建 `/etc/systemd/system/remote-control-server.service`：

```ini
[Unit]
Description=Remote Control Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/remote-control
Environment="PATH=/opt/remote-control/server/venv/bin"
ExecStart=/opt/remote-control/server/venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable remote-control-server
sudo systemctl start remote-control-server
sudo systemctl status remote-control-server
```

### 使用 systemd 管理客户端

创建 `/etc/systemd/system/remote-control-client.service`：

```ini
[Unit]
Description=Remote Control Client
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/remote-control/client
Environment="PATH=/opt/remote-control/client/venv/bin"
Environment="XDG_RUNTIME_DIR=/run/user/1000"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
ExecStart=/opt/remote-control/client/venv/bin/python -m client.main /etc/remote-control/client.conf
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable remote-control-client
sudo systemctl start remote-control-client
sudo systemctl status remote-control-client
```

### 使用 Nginx 反向代理

创建 `/etc/nginx/sites-available/remote-control`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /opt/remote-control/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # 健康检查
    location /health {
        proxy_pass http://localhost:8000;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/remote-control /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 配置 HTTPS（Let's Encrypt）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo systemctl reload nginx
```

## 配置说明

### 服务器配置

服务器配置通过环境变量或配置文件：

```bash
# 数据库路径
DATABASE_URL=sqlite+aiosqlite:///./remote_control.db

# JWT 密钥（生产环境必须修改）
SECRET_KEY=your-secret-key-here

# 日志级别
LOG_LEVEL=INFO
```

### 客户端配置

编辑 `/etc/remote-control/client.conf`：

```json
{
  "server_url": "https://your-domain.com",
  "device_name": "Office Desktop",
  "heartbeat_interval": 30,
  "reconnect_delay": 5,
  "max_reconnect_attempts": 6,
  "video_width": 1920,
  "video_height": 1080,
  "video_fps": 30,
  "video_bitrate": 2000000,
  "enable_audio": true,
  "enable_clipboard": true,
  "enable_file_transfer": true
}
```

## 安全建议

1. **修改默认密码**：首次登录后立即修改管理员密码
2. **使用 HTTPS**：生产环境必须启用 HTTPS
3. **防火墙配置**：仅开放必要端口（80, 443）
4. **定期备份**：备份数据库文件
5. **日志监控**：定期检查审计日志
6. **更新依赖**：定期更新 Python 和 npm 包

## 故障排查

### 服务器无法启动

```bash
# 检查日志
sudo journalctl -u remote-control-server -f

# 检查端口占用
sudo netstat -tlnp | grep 8000

# 检查数据库权限
ls -la /opt/remote-control/server/*.db
```

### 客户端无法连接

```bash
# 检查日志
sudo journalctl -u remote-control-client -f

# 测试网络连接
curl http://your-server:8000/health

# 检查配置文件
cat /etc/remote-control/client.conf
```

### WebSocket 连接失败

```bash
# 检查 Nginx 配置
sudo nginx -t

# 检查 WebSocket 代理
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  http://your-server/ws?token=test
```

## 性能优化

### 服务器优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# 优化 TCP 参数
sudo sysctl -w net.core.somaxconn=1024
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=2048
```

### 数据库优化

```bash
# 定期清理旧数据
sqlite3 remote_control.db "DELETE FROM performance_metrics WHERE timestamp < datetime('now', '-7 days');"
sqlite3 remote_control.db "DELETE FROM audit_logs WHERE timestamp < datetime('now', '-90 days');"
sqlite3 remote_control.db "VACUUM;"
```

## 监控和维护

### 健康检查

```bash
# 检查服务器状态
curl http://localhost:8000/health

# 检查连接数
curl http://localhost:8000/health | jq '.connections'
```

### 日志轮转

创建 `/etc/logrotate.d/remote-control`：

```
/var/log/remote-control/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload remote-control-server
    endscript
}
```

## 备份和恢复

### 备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR=/backup/remote-control
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份数据库
cp /opt/remote-control/server/remote_control.db $BACKUP_DIR/db_$DATE.db

# 备份配置
tar czf $BACKUP_DIR/config_$DATE.tar.gz /etc/remote-control/

# 删除 30 天前的备份
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

### 恢复

```bash
# 停止服务
sudo systemctl stop remote-control-server

# 恢复数据库
cp /backup/remote-control/db_YYYYMMDD_HHMMSS.db /opt/remote-control/server/remote_control.db

# 启动服务
sudo systemctl start remote-control-server
```
