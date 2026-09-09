# WaterExpert API 部署指南

## 方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| tmux | 简单快速 | 手动管理，服务器重启后需要重新启动 | 临时测试、开发环境 |
| systemd | 开机自启，自动重启，日志管理 | 需要root权限配置 | 生产环境 |
| Docker | 环境隔离，易迁移 | 需要学习Docker | 多环境部署 |
| screen | 类似tmux | 功能较少 | tmux的替代方案 |

---

## 方案1：tmux 后台运行（推荐新手）

### 1.1 安装tmux

```bash
# Ubuntu/Debian
sudo apt-get install tmux

# CentOS/RHEL
sudo yum install tmux
```

### 1.2 启动服务

```bash
# 创建启动脚本
cd /home/xchen2/WaterExpert-main

# 创建tmux会话并启动服务
tmux new -s water-api -d
tmux send-keys -t water-api "cd /home/xchen2/WaterExpert-main" C-m
tmux send-keys -t water-api "export DEEPSEEK_API_KEY='your-api-key-here'" C-m
tmux send-keys -t water-api "PYTHONPATH=src:\$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000" C-m
```

### 1.3 常用命令

```bash
# 查看所有会话
tmux ls

# 连接到会话（查看日志）
tmux attach -t water-api

# 退出但保持运行
# 在tmux内按: Ctrl+B 然后按 D

# 停止服务
tmux kill-session -t water-api
```

### 1.4 自动启动脚本

创建一个启动脚本方便使用：

```bash
#!/bin/bash
# start_water_api.sh

cd /home/xchen2/WaterExpert-main

# 检查会话是否已存在
if tmux has-session -t water-api 2>/dev/null; then
    echo "✗ 服务已在运行"
    echo "  使用 'tmux attach -t water-api' 查看"
    exit 1
fi

# 创建新会话
echo "🚀 启动 Water AI API 服务..."
tmux new -s water-api -d
tmux send-keys -t water-api "cd /home/xchen2/WaterExpert-main" C-m
tmux send-keys -t water-api "export DEEPSEEK_API_KEY='$DEEPSEEK_API_KEY'" C-m
tmux send-keys -t water-api "PYTHONPATH=src:\$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000" C-m

sleep 2
echo "✓ 服务已启动"
echo "  查看日志: tmux attach -t water-api"
echo "  停止服务: tmux kill-session -t water-api"
```

停止脚本：

```bash
#!/bin/bash
# stop_water_api.sh

if tmux has-session -t water-api 2>/dev/null; then
    echo "🛑 停止 Water AI API 服务..."
    tmux kill-session -t water-api
    echo "✓ 服务已停止"
else
    echo "✗ 服务未运行"
fi
```

---

## 方案2：systemd 服务（推荐生产环境）

### 2.1 配置服务文件

已生成: `water-ai-api.service`

**重要：修改其中的API密钥！**

### 2.2 安装服务

```bash
# 1. 编辑服务文件，填入真实的API密钥
nano /home/xchen2/WaterExpert-main/water-ai-api.service

# 2. 复制到systemd目录（需要root权限）
sudo cp /home/xchen2/WaterExpert-main/water-ai-api.service /etc/systemd/system/

# 3. 重新加载systemd配置
sudo systemctl daemon-reload

# 4. 启动服务
sudo systemctl start water-ai-api

# 5. 设置开机自启
sudo systemctl enable water-ai-api

# 6. 查看服务状态
sudo systemctl status water-ai-api
```

### 2.3 常用命令

```bash
# 启动服务
sudo systemctl start water-ai-api

# 停止服务
sudo systemctl stop water-ai-api

# 重启服务
sudo systemctl restart water-ai-api

# 查看状态
sudo systemctl status water-ai-api

# 查看日志
sudo journalctl -u water-ai-api -f

# 查看最近100行日志
sudo journalctl -u water-ai-api -n 100

# 禁用开机自启
sudo systemctl disable water-ai-api
```

---

## 方案3：Docker 部署

### 3.1 创建Dockerfile

已在API文档中提供，位置：API_GUIDE.md

### 3.2 构建和运行

```bash
cd /home/xchen2/WaterExpert-main

# 构建镜像
docker build -t water-ai-api .

# 运行容器
docker run -d \
  --name water-ai-api \
  -p 8000:8000 \
  -e DEEPSEEK_API_KEY="your-api-key" \
  -v $(pwd)/outputs:/app/outputs \
  --restart unless-stopped \
  water-ai-api

# 查看日志
docker logs -f water-ai-api

# 停止容器
docker stop water-ai-api

# 启动容器
docker start water-ai-api
```

---

## 验证服务运行

无论使用哪种方案，启动后都应该验证：

```bash
# 1. 检查端口是否监听
netstat -tuln | grep 8000
# 或
ss -tuln | grep 8000

# 2. 测试健康检查
curl http://localhost:8000/api/health

# 3. 从外部测试（替换为你的服务器IP）
curl http://your-server-ip:8000/api/health

# 4. 运行完整测试
cd /home/xchen2/WaterExpert-main
python test_api.py
```

---

## 安全建议

### 1. 防火墙配置

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8000/tcp
sudo ufw status

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 2. 仅允许特定IP访问

```bash
# 只允许合作方IP访问
sudo ufw allow from 合作方IP to any port 8000
```

### 3. 使用Nginx反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api {
        proxy_pass http://localhost:8000/api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 监控和维护

### 检查服务健康

```bash
# 创建健康检查脚本
cat > check_health.sh << 'EOF'
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health)
if [ "$response" = "200" ]; then
    echo "✓ 服务正常运行"
else
    echo "✗ 服务异常 (HTTP $response)"
    # 可以在这里添加重启逻辑或发送告警
fi
EOF

chmod +x check_health.sh

# 添加到crontab，每5分钟检查一次
# crontab -e
# */5 * * * * /home/xchen2/WaterExpert-main/check_health.sh
```

---

## 故障排除

### 服务无法启动

```bash
# 检查端口是否被占用
sudo lsof -i :8000

# 检查Python环境
which python
python --version

# 检查依赖是否安装
pip list | grep fastapi
pip list | grep uvicorn

# 重新安装依赖
pip install -r requirements-api.txt
```

### 无法从外部访问

```bash
# 1. 检查服务是否监听所有接口
netstat -tuln | grep 8000
# 应该显示 0.0.0.0:8000，而不是 127.0.0.1:8000

# 2. 检查防火墙
sudo ufw status
sudo iptables -L -n | grep 8000

# 3. 测试网络连通性
ping your-server-ip
telnet your-server-ip 8000
```

---

## 提供给合作方的信息

创建一个文档给合作方：

```markdown
# Water AI API 接入文档

## 基础信息
- API地址: http://your-server-ip:8000/api
- 在线文档: http://your-server-ip:8000/docs
- 支持: 联系方式

## 快速开始
1. 访问在线文档查看所有端点
2. 测试健康检查: GET /api/health
3. 查看可用场景: GET /api/scenarios
4. 生成策略: POST /api/strategy

## 示例代码
参见 API_GUIDE.md

## 限流说明
- 每秒最多X个请求
- 单个任务处理时间约2-5秒

## 支持的场景
- S1: 外源输入型
- S2: 内源释放型
- S3: 藻类暴发型
- S4: 慢性综合型
```

---

**建议**: 如果是临时测试，用tmux即可；如果是长期稳定服务，使用systemd。
