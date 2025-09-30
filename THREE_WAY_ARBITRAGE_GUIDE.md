# 三方套利使用指南

## 概述

本系统现在支持完整的三方套利功能：Aster + OKX + Backpack，提供更多的套利机会和更低的交易成本。

## 快速开始

### 1. 安装依赖

```bash
# 安装Backpack依赖
./install_backpack_deps.sh

# 或手动安装
pip3 install cryptography
```

### 2. 配置账户

#### 添加Aster账户
```bash
python3 -m src.main account add-aster --name "Aster-1" --api-key "your_api_key" --secret "your_secret"
```

#### 添加OKX账户
```bash
python3 -m src.main account add-okx --name "OKX-1" --api-key "your_api_key" --secret "your_secret" --passphrase "your_passphrase"
```

#### 添加Backpack账户
```bash
python3 -m src.main account add-backpack --name "Backpack-1" --api-key "your_api_key" --secret "your_ed25519_private_key_base64"
```

### 3. 查看账户

```bash
python3 -m src.main account list
```

## 套利交易命令

### 双方套利（Aster + OKX）

```bash
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --min-spread 0.5 \
  --aster-account 1 \
  --okx-account 2 \
  --real-trade
```

### 三方套利（Aster + OKX + Backpack）

```bash
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --min-spread 0.5 \
  --aster-account 1 \
  --okx-account 2 \
  --backpack-account 3 \
  --real-trade
```

### 任意组合套利

```bash
# Aster + Backpack
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --aster-account 1 \
  --backpack-account 3 \
  --real-trade

# OKX + Backpack
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --okx-account 2 \
  --backpack-account 3 \
  --real-trade
```

## 费率对比

| 交易所 | Maker | Taker | 特点 |
|--------|-------|-------|------|
| Aster | 0.01% | 0.035% | 稳定可靠 |
| OKX | -0.005% | 0.015% | 有返佣 |
| Backpack | 0.01% | 0.02% | 新兴交易所 |

## 交易对格式

| 交易所 | 格式 | 示例 |
|--------|------|------|
| Aster | BTCUSDT | BTCUSDT |
| OKX | BTC/USDT:USDT | BTC/USDT:USDT |
| Backpack | BTC_USDC | BTC_USDC |

## 风险控制

### 自动风险控制
- **零单边风险** - 一方成交立即对冲另一方
- **动态价格跟踪** - 价格偏移时自动调整订单
- **智能重新下单** - 确保最优成交价格
- **异常恢复** - 网络异常时自动重试

### 手动风险控制
- **实时监控** - 持续监控持仓状态
- **自动平仓** - 价差回归或止损时自动平仓
- **紧急停止** - Ctrl+C 安全停止交易

## 测试功能

### 运行测试脚本

```bash
python3 test_three_way_arbitrage.py
```

### 模拟交易

```bash
# 不添加 --real-trade 参数进行模拟
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --aster-account 1 \
  --okx-account 2 \
  --backpack-account 3
```

## 高级功能

### 自定义价差阈值

```bash
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --min-spread 1.0 \
  --aster-account 1 \
  --okx-account 2 \
  --backpack-account 3 \
  --real-trade
```

### 不同杠杆设置

```bash
# 低风险
python3 -m src.main arbitrage execute -s BTCUSDT -a 0.01 -l 1 --aster-account 1 --okx-account 2 --real-trade

# 高风险
python3 -m src.main arbitrage execute -s BTCUSDT -a 0.01 -l 10 --aster-account 1 --okx-account 2 --real-trade
```

## 故障排除

### 常见问题

1. **cryptography未安装**
   ```bash
   pip3 install cryptography
   ```

2. **账户配置错误**
   ```bash
   # 检查账户配置
   python3 -m src.main account list
   ```

3. **API密钥错误**
   - 检查API Key格式
   - 确认Private Key是Base64编码的Ed25519密钥

4. **网络连接问题**
   - 检查网络连接
   - 确认API访问权限

### 调试模式

```bash
# 启用详细日志
export DEBUG=1
python3 -m src.main arbitrage execute ...
```

## 最佳实践

### 1. 风险管理
- 从小额开始测试
- 设置合理的止损阈值
- 监控市场波动

### 2. 成本优化
- 优先使用Maker订单
- 选择费率最低的组合
- 避免频繁交易

### 3. 系统监控
- 定期检查账户状态
- 监控系统性能
- 及时处理异常

## 更新日志

- **v1.0.0** - 初始三方套利支持
  - 支持Aster + OKX + Backpack
  - 实现动态价格跟踪
  - 集成风险控制机制

## 技术支持

如有问题，请检查：
1. 依赖是否正确安装
2. 账户配置是否正确
3. 网络连接是否正常
4. 交易对格式是否正确
