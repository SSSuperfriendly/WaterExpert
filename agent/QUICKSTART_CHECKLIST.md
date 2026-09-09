# 🚀 WaterExpert API 快速启动清单

## 📋 提供给合作方接入 - 完整步骤

### ✅ 第一步：环境准备

```bash
# 1. 进入项目目录
cd /home/xchen2/WaterExpert-main

# 2. 安装API依赖
pip install -r requirements-api.txt

# 3. 设置DeepSeek API密钥（重要！）
export DEEPSEEK_API_KEY="sk-your-api-key-here"

# 或者写入 ~/.bashrc 永久生效
echo 'export DEEPSEEK_API_KEY="sk-your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

---

### ✅ 第二步：启动服务（选择一种方式）

#### 方式A：使用tmux（推荐，简单快速）

```bash
# 启动服务
./start_water_api.sh

# 查看状态
./check_water_api.sh

# 查看日志
tmux attach -t water-api
# 退出日志但保持运行：按 Ctrl+B 然后按 D

# 停止服务
./stop_water_api.sh
```

#### 方式B：直接运行（前台，会占用终端）

```bash
PYTHONPATH=src:$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000
# 按 Ctrl+C 停止
```

#### 方式C：使用systemd（生产环境，开机自启）

```bash
# 1. 编辑服务文件，填入真实API密钥
nano water-ai-api.service

# 2. 安装服务
sudo cp water-ai-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start water-ai-api
sudo systemctl enable water-ai-api

# 3. 查看状态
sudo systemctl status water-ai-api

# 4. 查看日志
sudo journalctl -u water-ai-api -f
```

---

### ✅ 第三步：验证服务

```bash
# 1. 检查端口监听
netstat -tuln | grep 8000
# 或
ss -tuln | grep 8000

# 2. 本地测试
curl http://localhost:8000/api/health

# 3. 外部测试（替换为你的服务器IP）
curl http://your-server-ip:8000/api/health

# 4. 完整功能测试
python test_api.py
```

---

### ✅ 第四步：配置防火墙（重要！）

```bash
# Ubuntu/Debian
sudo ufw allow 8000/tcp
sudo ufw status

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload

# 如果只允许特定IP访问（更安全）
sudo ufw allow from 合作方IP to any port 8000
```

---

### ✅ 第五步：提供给合作方的信息

创建一个文档发送给合作方，包含以下内容：

```markdown
# WaterExpert Agent 接入信息

## 服务地址
- **API地址**: http://你的服务器IP:8000/api
- **在线文档**: http://你的服务器IP:8000/docs
- **技术文档**: 附件 INTEGRATION_GUIDE.md

## 快速测试

### 1. 健康检查
curl http://你的服务器IP:8000/api/health

### 2. 查看场景
curl http://你的服务器IP:8000/api/scenarios

### 3. 生成策略示例
curl -X POST http://你的服务器IP:8000/api/strategy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "s1_external_input",
    "state": {
      "date": "2025-10-31",
      "turbidity": 25.5,
      "flow_rate": 28.5
    },
    "episodes": 1,
    "backend": "api"
  }'

## 支持的场景
- s1_external_input: 外源输入型
- s2_internal_release: 内源释放型  
- s3_algae_bloom: 藻类暴发型
- s4_chronic_combo: 慢性综合型

## 技术支持
- 联系人: [你的名字]
- 邮箱: [你的邮箱]
- 电话: [你的电话]
```

---

## 📁 需要发送给合作方的文件

1. ✅ **INTEGRATION_GUIDE.md** - 详细接入文档（已生成）
2. ✅ **API_GUIDE.md** - API完整指南（已存在）
3. ⚠️ **接入信息文档** - 包含你的实际服务器IP和联系方式

---

## 🔍 日常运维

### 查看服务状态
```bash
./check_water_api.sh
```

### 查看日志
```bash
# tmux方式
tmux attach -t water-api

# systemd方式
sudo journalctl -u water-ai-api -f

# 查看最近100行
sudo journalctl -u water-ai-api -n 100
```

### 重启服务
```bash
# tmux方式
./stop_water_api.sh
./start_water_api.sh

# systemd方式
sudo systemctl restart water-ai-api
```

### 检查服务健康（定时任务）
```bash
# 添加到crontab，每5分钟检查一次
crontab -e

# 添加这一行
*/5 * * * * curl -s http://localhost:8000/api/health > /dev/null || echo "API服务异常" | mail -s "WaterExpert告警" your-email@example.com
```

---

## ⚠️ 常见问题

### 1. 服务无法启动

**问题**: 运行start_water_api.sh后服务没有响应

**排查**:
```bash
# 检查端口是否被占用
sudo lsof -i :8000

# 查看tmux会话
tmux attach -t water-api
# 查看错误信息

# 检查依赖
pip list | grep fastapi
pip list | grep uvicorn
```

**解决**: 
```bash
# 重新安装依赖
pip install -r requirements-api.txt
```

---

### 2. 外部无法访问

**问题**: 本地curl成功，但合作方无法访问

**排查**:
```bash
# 1. 确认服务监听0.0.0.0而不是127.0.0.1
netstat -tuln | grep 8000
# 应该看到: 0.0.0.0:8000

# 2. 检查防火墙
sudo ufw status
sudo iptables -L -n | grep 8000

# 3. 测试网络连通性
ping your-server-ip
telnet your-server-ip 8000
```

**解决**:
```bash
# 开放防火墙
sudo ufw allow 8000/tcp

# 重启服务，确保使用 --host 0.0.0.0
./stop_water_api.sh
./start_water_api.sh
```

---

### 3. API密钥未设置

**问题**: 启动时提示 "DEEPSEEK_API_KEY not set"

**解决**:
```bash
# 临时设置（当前会话）
export DEEPSEEK_API_KEY="sk-your-key"

# 永久设置
echo 'export DEEPSEEK_API_KEY="sk-your-key"' >> ~/.bashrc
source ~/.bashrc

# 验证
echo $DEEPSEEK_API_KEY
```

---

### 4. 服务突然停止

**问题**: 服务运行一段时间后自动停止

**原因**: 可能是：
- 服务器重启了
- 进程被杀死
- 内存不足

**解决**: 使用systemd代替tmux（自动重启）
```bash
# 切换到systemd
./stop_water_api.sh
sudo systemctl start water-ai-api
sudo systemctl enable water-ai-api
```

---

## 📊 监控建议

### 简单监控脚本
```bash
#!/bin/bash
# monitor_api.sh

while true; do
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health)
    
    if [ "$response" != "200" ]; then
        echo "[$(date)] ⚠️  API异常 (HTTP $response)" >> /var/log/water-api-monitor.log
        # 可以在这里添加告警通知
    else
        echo "[$(date)] ✓ API正常" >> /var/log/water-api-monitor.log
    fi
    
    sleep 300  # 每5分钟检查一次
done
```

---

## 📞 支持联系

如果遇到无法解决的问题：

1. 查看详细文档：
   - [deploy_guide.md](deploy_guide.md)
   - [API_GUIDE.md](API_GUIDE.md)
   - [API_ARCHITECTURE.md](API_ARCHITECTURE.md)

2. 查看在线文档：
   - http://localhost:8000/docs

3. 联系技术支持：
   - [填写你的联系方式]

---

## ✅ 检查清单

在提供给合作方前，确认以下项目：

- [ ] 服务已启动并正常运行
- [ ] 防火墙已配置
- [ ] 健康检查接口正常响应
- [ ] 完整测试通过 (python test_api.py)
- [ ] 合作方IP已加入白名单（如果有限制）
- [ ] 已准备好接入文档
- [ ] 已测试从外部网络访问
- [ ] 已设置监控或定时检查
- [ ] 已准备好技术支持联系方式

---

**完成以上步骤后，你就可以将服务URL和文档提供给合作方了！** 🎉
