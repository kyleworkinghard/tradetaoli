#!/bin/bash

# Backpack交易所依赖安装脚本

echo "🚀 安装Backpack交易所依赖..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo "📋 Python版本: $python_version"

# 安装cryptography
echo "📦 安装cryptography..."
pip3 install cryptography

# 验证安装
echo "✅ 验证安装..."
python3 -c "
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    print('✅ cryptography安装成功')
except ImportError as e:
    print('❌ cryptography安装失败:', e)
    exit(1)
"

echo "🎉 Backpack交易所支持已启用！"
echo ""
echo "现在您可以："
echo "1. 添加Backpack账户: python3 -m src.main account add-backpack"
echo "2. 运行三方套利: python3 -m src.main arbitrage execute --backpack-account 3"
echo "3. 查看支持的交易所: python3 -m src.main account list"
