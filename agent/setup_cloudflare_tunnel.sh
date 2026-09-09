#!/bin/bash
# Cloudflare Tunnel 安装和配置脚本

echo "==================================="
echo "Cloudflare Tunnel 安装向导"
echo "==================================="
echo ""

# 1. 下载 cloudflared
echo "步骤 1/4: 下载 cloudflared..."
cd /home/xchen2/WaterExpert-main

if [ -f "cloudflared" ]; then
    echo "✓ cloudflared 已存在"
else
    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x cloudflared-linux-amd64
    mv cloudflared-linux-amd64 cloudflared
    echo "✓ cloudflared 下载完成"
fi
echo ""

# 2. 登录说明
echo "步骤 2/4: 登录 Cloudflare"
echo "请执行以下命令进行登录（会打开浏览器）："
echo ""
echo "  ./cloudflared tunnel login"
echo ""
echo "如果服务器没有浏览器，会显示一个URL，复制到本地浏览器打开"
echo ""
echo "登录后会下载证书到 ~/.cloudflared/cert.pem"
echo ""
read -p "按 Enter 继续..."
./cloudflared tunnel login
echo ""

# 3. 创建tunnel
echo "步骤 3/4: 创建 Tunnel"
read -p "请输入tunnel名称（例如：water-api）: " TUNNEL_NAME

if [ -z "$TUNNEL_NAME" ]; then
    TUNNEL_NAME="water-api"
    echo "使用默认名称: water-api"
fi

./cloudflared tunnel create $TUNNEL_NAME
echo ""

# 4. 配置说明
echo "步骤 4/4: 配置 Tunnel"
echo ""
echo "接下来需要："
echo "1. 在 Cloudflare 控制台添加域名"
echo "2. 或使用 Cloudflare 提供的临时域名"
echo ""
echo "创建配置文件..."

mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << EOF
tunnel: $TUNNEL_NAME
credentials-file: /home/xchen2/.cloudflared/$(ls ~/.cloudflared/*.json | head -1 | xargs basename)

ingress:
  - hostname: CHANGE_THIS_TO_YOUR_DOMAIN
    service: http://localhost:8000
  - service: http_status:404
EOF

echo "✓ 配置文件已创建: ~/.cloudflared/config.yml"
echo ""
echo "==================================="
echo "下一步："
echo "1. 如果你有域名，在 Cloudflare 添加 DNS 记录"
echo "2. 编辑 ~/.cloudflared/config.yml，修改 CHANGE_THIS_TO_YOUR_DOMAIN"
echo "3. 运行: ./cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "或者使用快速临时域名："
echo "  ./cloudflared tunnel --url http://localhost:8000"
echo "==================================="
