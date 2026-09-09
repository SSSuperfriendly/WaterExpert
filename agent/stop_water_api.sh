#!/bin/bash
# Water AI API 停止脚本

if tmux has-session -t water-api 2>/dev/null; then
    echo "🛑 停止 Water AI API 服务..."
    tmux kill-session -t water-api
    echo "✓ 服务已停止"
else
    echo "✗ 服务未运行"
    echo "  启动服务: ./start_water_api.sh"
fi
