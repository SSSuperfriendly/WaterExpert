#!/bin/bash
# Water AI API 状态检查脚本

echo "==================================="
echo "Water AI API 服务状态检查"
echo "==================================="
echo ""

# 1. 检查tmux会话
echo "1. tmux会话状态:"
if tmux has-session -t water-api 2>/dev/null; then
    echo "   ✓ tmux会话运行中"
else
    echo "   ✗ tmux会话未运行"
fi
echo ""

# 2. 检查端口
echo "2. 端口监听状态:"
if netstat -tuln 2>/dev/null | grep -q ":8000 "; then
    echo "   ✓ 端口8000正在监听"
    netstat -tuln | grep ":8000 "
elif ss -tuln 2>/dev/null | grep -q ":8000 "; then
    echo "   ✓ 端口8000正在监听"
    ss -tuln | grep ":8000 "
else
    echo "   ✗ 端口8000未监听"
fi
echo ""

# 3. 检查API健康
echo "3. API健康检查:"
response=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/health 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" = "200" ]; then
    echo "   ✓ API正常响应 (HTTP 200)"
    echo "   响应: $body"
else
    echo "   ✗ API异常 (HTTP $http_code)"
fi
echo ""

# 4. 提示信息
echo "==================================="
echo "常用命令:"
echo "  启动服务: ./start_water_api.sh"
echo "  停止服务: ./stop_water_api.sh"
echo "  查看日志: tmux attach -t water-api"
echo "  测试API:  python test_api.py"
echo "==================================="
