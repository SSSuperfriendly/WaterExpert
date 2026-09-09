#!/bin/bash
# Water AI API 启动脚本

cd /home/xchen2/WaterExpert-main

# 检查tmux是否安装
if ! command -v tmux &> /dev/null; then
    echo "✗ tmux 未安装"
    echo "  请运行: sudo apt-get install tmux"
    exit 1
fi

# 检查会话是否已存在
if tmux has-session -t water-api 2>/dev/null; then
    echo "✗ 服务已在运行"
    echo "  查看日志: tmux attach -t water-api"
    echo "  停止服务: ./stop_water_api.sh"
    exit 1
fi

# 检查API密钥
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "⚠ DEEPSEEK_API_KEY 未设置"
    echo "  建议先设置: export DEEPSEEK_API_KEY='your-key-here'"
    echo "  或继续使用mock模式（按Enter继续，Ctrl+C取消）"
    read -r
fi

# 创建新会话并启动服务
echo "🚀 启动 Water AI API 服务..."
tmux new -s water-api -d
tmux send-keys -t water-api "cd /home/xchen2/WaterExpert-main" C-m
tmux send-keys -t water-api "export DEEPSEEK_API_KEY='$DEEPSEEK_API_KEY'" C-m
tmux send-keys -t water-api "PYTHONPATH=src:\$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000" C-m

# 等待服务启动
sleep 3

# 测试服务是否正常
echo ""
echo "正在检查服务状态..."
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✓ 服务启动成功！"
    echo ""
    echo "📖 API文档: http://localhost:8000/docs"
    echo "🔍 查看日志: tmux attach -t water-api"
    echo "🛑 停止服务: ./stop_water_api.sh"
    echo ""
    echo "提示: 在tmux中按 Ctrl+B 然后按 D 可以退出但保持服务运行"
else
    echo "⚠ 服务可能未正常启动，请查看日志"
    echo "  tmux attach -t water-api"
fi
