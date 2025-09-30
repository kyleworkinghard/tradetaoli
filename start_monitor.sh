#!/bin/bash

# 价差监控启动脚本
# 使用方法: ./start_monitor.sh

echo "╔═══════════════════════════════════════╗"
echo "║        价差监控系统启动器              ║"
echo "║    Aster & Backpack 价差实时监控      ║"
echo "╚═══════════════════════════════════════╝"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未找到，请先安装 Python 3.7+"
    exit 1
fi

# 检查依赖包
echo "🔍 检查Python依赖包..."
python3 -c "import pandas, matplotlib, seaborn" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 安装必要的依赖包..."
    pip3 install pandas matplotlib seaborn
fi

# 创建数据目录
mkdir -p spread_data

echo "🚀 启动价差数据记录器..."
echo "📊 记录 BTC 和 ETH 合约价差数据"
echo "📁 数据保存位置: ./spread_data/"
echo "⏹️  按 Ctrl+C 停止记录"
echo ""

# 启动监控程序
python3 mark.py

echo ""
echo "🏁 价差监控已停止"
echo "📊 使用以下命令分析数据:"
echo "   python3 analyze.py              # 分析所有数据"
echo "   python3 analyze.py --symbol BTC # 只分析BTC数据"
echo "   python3 analyze.py --days 1     # 只分析最近1天数据"