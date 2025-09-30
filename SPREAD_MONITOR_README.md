# 价差监控与分析系统

用于记录和分析Aster与Backpack交易所之间的BTC、ETH合约价差数据，发现套利机会和价差规律。

## 📁 文件说明

- `mark.py` - 价差数据记录器（主要脚本）
- `analyze.py` - 价差数据分析器
- `start_monitor.sh` - 一键启动脚本
- `spread_data/` - 数据存储目录（自动创建）

## 🚀 快速开始

### 方法1：使用启动脚本（推荐）
```bash
./start_monitor.sh
```

### 方法2：直接运行Python脚本
```bash
python3 mark.py
```

## 📊 数据记录功能

### 记录内容
- **BTC/USDT** 合约价差
- **ETH/USDT** 合约价差
- 实时盘口数据（买一、卖一价格）
- 双向价差计算
- 最佳套利方向识别

### 数据格式
CSV文件包含以下字段：
```
timestamp, datetime, symbol,
aster_bid, aster_ask, aster_mid,
backpack_bid, backpack_ask, backpack_mid,
spread_1, spread_2, best_spread, best_direction
```

### 记录参数
- **记录间隔**: 1秒
- **文件命名**: `spread_{SYMBOL}_{TIMESTAMP}.csv`
- **自动保存**: 实时写入磁盘
- **运行统计**: 显示记录数、运行时间等

## 📈 数据分析功能

### 基础分析
```bash
# 分析所有数据
python3 analyze.py

# 只分析BTC数据
python3 analyze.py --symbol BTCUSDT

# 分析最近3天数据
python3 analyze.py --days 3

# 设置最小套利价差为2美元
python3 analyze.py --min-spread 2.0
```

### 分析内容

#### 1. 基础统计分析
- 记录条数统计
- 时间范围分析
- 价差均值、标准差
- 套利机会频率

#### 2. 价差分布分析
- 价差分布直方图
- 盈利区间标识
- 双向价差对比

#### 3. 时间序列分析
- 价差时间走势图
- 盈利区域高亮显示
- 分钟级数据重采样

#### 4. 套利机会分析
- 套利机会次数统计
- 平均价差计算
- 持续时间分析
- 详细机会列表导出

#### 5. 相关性分析
- 不同交易对价差相关性
- 相关性矩阵热力图
- 市场关联度评估

### 输出文件
- `spread_distribution.png` - 价差分布图
- `spread_timeseries.png` - 时间序列图
- `correlation_matrix.png` - 相关性矩阵图
- `arbitrage_opportunities_{SYMBOL}.csv` - 套利机会详情
- `analysis_report.txt` - 完整分析报告

## ⚙️ 配置要求

### Python依赖
```bash
pip3 install pandas matplotlib seaborn asyncio
```

### 账户配置
确保 `accounts.json` 中配置了Aster和Backpack账户信息：
```json
[
  {
    "id": 5,
    "exchange": "Aster",
    "api_key": "your_aster_api_key",
    "secret_key": "your_aster_secret"
  },
  {
    "id": 6,
    "exchange": "Backpack",
    "api_key": "your_backpack_api_key",
    "secret_key": "your_backpack_secret"
  }
]
```

## 📊 实际使用示例

### 启动监控
```bash
./start_monitor.sh
```

输出示例：
```
📊 开始记录价差数据...
📊 监控品种: BTCUSDT, ETHUSDT
📊 记录间隔: 1秒
📊 数据保存: /path/to/spread_data

[14:25:30] BTCUSDT | A买→B卖: 🔴-2.50 | B买→A卖: 🟢+3.20 | 最佳: +3.20 | 记录数: 150 | 运行时间: 150s
[14:25:31] ETHUSDT | A买→B卖: 🟢+1.80 | B买→A卖: 🔴-0.90 | 最佳: +1.80 | 记录数: 151 | 运行时间: 151s
```

### 数据分析
运行一天后分析数据：
```bash
python3 analyze.py --days 1
```

分析结果示例：
```
📊 基础统计分析
🔸 BTCUSDT 统计信息:
   记录条数: 86,400
   时间范围: 2024-01-01 00:00:00 ~ 2024-01-02 00:00:00

   价差统计:
   方向1 (A买→B卖): 均值-0.50, 标准差2.30
   方向2 (B买→A卖): 均值+0.80, 标准差1.90
   最佳价差: 均值+1.20, 标准差2.10

   套利机会 (价差>1美元):
   A买→B卖: 1,250 次 (1.4%)
   B买→A卖: 2,800 次 (3.2%)
   总计: 4,050 次 (4.7%)
```

## 🎯 应用场景

### 1. 套利策略开发
- 识别最佳套利时机
- 评估价差持续时间
- 优化进出场策略

### 2. 风险管理
- 了解价差波动范围
- 设定合理的止损位
- 评估市场流动性

### 3. 市场研究
- 分析不同时段的价差特征
- 研究新闻事件对价差的影响
- 建立价差预测模型

### 4. 回测分析
- 基于历史数据验证策略
- 计算理论收益率
- 优化交易参数

## ⚠️ 注意事项

1. **网络延迟**: 记录的价差数据包含网络延迟，实际交易时需考虑
2. **API限制**: 注意交易所API调用频率限制
3. **数据存储**: 长期运行会产生大量数据文件
4. **交易成本**: 分析时需考虑手续费、滑点等交易成本
5. **市场风险**: 价差数据仅供参考，实际交易存在风险

## 🔧 高级配置

### 自定义记录间隔
修改 `mark.py` 中的 `record_interval` 参数：
```python
self.record_interval = 0.5  # 改为0.5秒记录一次
```

### 添加更多交易对
修改 `mark.py` 中的 `symbols` 列表：
```python
self.symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']  # 添加SOL
```

### 自定义分析阈值
```bash
python3 analyze.py --min-spread 5.0  # 设置5美元为最小套利阈值
```

## 🆘 故障排除

### 常见问题

1. **连接失败**
   - 检查网络连接
   - 验证API密钥正确性
   - 确认账户权限

2. **数据缺失**
   - 检查磁盘空间
   - 验证写入权限
   - 查看错误日志

3. **分析失败**
   - 确认数据文件存在
   - 检查Python依赖包
   - 验证数据格式

### 日志信息
程序运行过程中会输出详细的状态信息，注意观察：
- ✅ 成功操作
- ⚠️ 警告信息
- ❌ 错误信息

---

**开发者**: GoodDEX CLI Team
**版本**: 1.0
**更新日期**: 2024-01-01