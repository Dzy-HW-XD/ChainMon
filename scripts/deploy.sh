#!/bin/bash
# =============================================
# ChainMon - 一键部署脚本
# 仅支持 Ubuntu 20.04/22.04
# =============================================

set -e

echo "============================================"
echo " ChainMon - 一键部署"
echo "============================================"

# 检查操作系统
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    echo "错误: 本系统仅支持 Ubuntu，当前系统不兼容"
    exit 1
fi

# 安装系统依赖
echo "[1/5] 安装系统依赖..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ipmitool openssh-client curl

# 创建虚拟环境
echo "[2/5] 创建Python虚拟环境..."
python3 -m venv venv

# 安装Python依赖
echo "[3/5] 安装Python依赖..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 创建必要目录
echo "[4/5] 创建数据目录..."
mkdir -p data/ledger data/cache logs config

# 初始化配置（如果不存在）
echo "[5/5] 初始化配置..."
if [ ! -f config/node_config.yaml ]; then
    cp config/config_template.yaml config/node_config.yaml
    echo "配置文件已创建: config/node_config.yaml"
    echo "请编辑配置文件后运行: source venv/bin/activate && python3 monitor_client.py"
else
    echo "配置文件已存在，跳过"
fi

echo ""
echo "============================================"
echo " 部署完成！"
echo "============================================"
echo ""
echo "启动方式："
echo "  前台测试: source venv/bin/activate && python3 monitor_client.py"
echo "  后台运行: nohup python3 monitor_client.py > logs/monitor.log 2>&1 &"
echo "  systemd:  sudo cp scripts/monitor.service /etc/systemd/system/ && sudo systemctl start monitor"
echo ""
echo "管理后台: http://服务器IP:5000"
echo "============================================"
