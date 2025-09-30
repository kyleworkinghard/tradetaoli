# Backpack交易所集成

## 概述

本项目现已支持Backpack交易所的合约交易功能，实现三方套利：Aster + OKX + Backpack。

## 特性

- ✅ **Ed25519签名** - 符合Backpack API安全要求
- ✅ **合约交易** - 支持永续合约和杠杆交易
- ✅ **风险控制** - 集成现有的对冲机制
- ✅ **三方套利** - 支持三个交易所同时套利
- ✅ **统一接口** - 与现有系统完全兼容

## 安装依赖

```bash
# 运行安装脚本
./install_backpack_deps.sh

# 或手动安装
pip3 install cryptography
```

## 配置Backpack账户

### 1. 获取API密钥

1. 登录 [Backpack交易所](https://backpack.exchange)
2. 进入API管理页面
3. 创建新的API密钥
4. 记录API Key和Private Key（Ed25519格式）

### 2. 添加账户

```bash
# 添加Backpack账户
python3 -m src.main account add-backpack \
  --name "Backpack-1" \
  --api-key "your_api_key" \
  --secret "your_ed25519_private_key_base64"
```

## 交易对格式

| 交易所 | 格式 | 示例 |
|--------|------|------|
| Aster | BTCUSDT | BTCUSDT |
| OKX | BTC/USDT:USDT | BTC/USDT:USDT |
| Backpack | BTC_USDC | BTC_USDC |

## 费率对比

| 交易所 | Maker | Taker |
|--------|-------|-------|
| Aster | 0.01% | 0.035% |
| OKX | -0.005% | 0.015% |
| Backpack | 0.01% | 0.02% |

## 三方套利示例

```bash
# 三方套利交易
python3 -m src.main arbitrage execute \
  -s BTCUSDT \
  -a 0.01 \
  -l 3 \
  --min-spread 0 \
  --aster-account 1 \
  --okx-account 2 \
  --backpack-account 3 \
  --real-trade
```

## 支持的API功能

### BackpackAdapter方法

- `test_connection()` - 测试连接
- `get_balance()` - 获取余额
- `get_positions()` - 获取持仓
- `get_orderbook()` - 获取盘口
- `place_order()` - 下单
- `cancel_order()` - 撤单
- `get_order_status()` - 获取订单状态
- `close_position()` - 平仓

## 风险控制

系统支持以下风险控制机制：

1. **零单边风险** - 一方成交立即对冲另一方
2. **动态价格跟踪** - 价格偏移时自动调整订单
3. **智能重新下单** - 确保最优成交价格
4. **异常恢复** - 网络异常时自动重试

## 故障排除

### 常见问题

1. **cryptography未安装**
   ```bash
   pip3 install cryptography
   ```

2. **API密钥错误**
   - 检查API Key格式
   - 确认Private Key是Base64编码的Ed25519密钥

3. **网络连接问题**
   - 检查网络连接
   - 确认API访问权限

### 调试模式

```bash
# 启用详细日志
export DEBUG=1
python3 -m src.main arbitrage execute ...
```

## 更新日志

- **v1.0.0** - 初始Backpack集成
  - 支持Ed25519签名
  - 实现合约交易功能
  - 集成三方套利系统

## 技术支持

如有问题，请检查：
1. 依赖是否正确安装
2. API密钥是否有效
3. 网络连接是否正常
4. 交易对格式是否正确
