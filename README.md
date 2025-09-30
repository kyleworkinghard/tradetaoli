# GoodDEX CLI - 专业双交易所对冲交易终端

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/gooddex/gooddex-cli)

GoodDEX CLI 是一个强大的命令行工具，专为专业交易者设计，支持 Aster 和 OKX 双交易所的自动化对冲交易。

## 🚀 特性

- **双交易所支持**: 同时支持 Aster DEX 和 OKX CEX
- **自动化对冲**: 智能监控价差，自动执行套利交易
- **实时监控**: 实时显示持仓、盈亏和市场数据
- **风险管理**: 内置止损、止盈和仓位管理
- **数据统计**: 完整的交易记录和绩效分析
- **安全认证**: 支持 API 密钥安全存储和管理
- **配置管理**: 灵活的配置文件和环境变量支持

## 📦 安装

### 从源码安装
```bash
git clone https://github.com/gooddex/gooddex-cli.git
cd gooddex-cli
pip install -e .
```

### 从 PyPI 安装
```bash
pip install gooddex-cli
```

## 🔧 快速开始

### 1. 初始化配置
```bash
gooddex config init
```

### 2. 添加交易账户
```bash
# 添加 Aster 账户
gooddex account add --name "aster-main" --exchange aster --api-key "your-api-key" --secret "your-secret"

# 添加 OKX 账户
gooddex account add --name "okx-main" --exchange okx --api-key "your-api-key" --secret "your-secret" --passphrase "your-passphrase"
```

### 3. 查看账户状态
```bash
gooddex account list
gooddex account balance --name "aster-main"
```

### 4. 创建交易会话
```bash
gooddex trading create-session \
  --name "BTC-套利-001" \
  --symbol "BTC/USDT" \
  --size 0.1 \
  --aster-account "aster-main" \
  --okx-account "okx-main" \
  --direction long
```

### 5. 启动交易
```bash
gooddex trading start --session-id 1
```

### 6. 监控交易
```bash
gooddex trading monitor --session-id 1
gooddex stats overview
```

## 📋 命令参考

### 认证管理
```bash
gooddex auth login                    # 登录系统
gooddex auth logout                   # 登出系统
gooddex auth status                   # 查看登录状态
```

### 账户管理
```bash
gooddex account list                  # 列出所有账户
gooddex account add                   # 添加新账户
gooddex account update                # 更新账户信息
gooddex account delete                # 删除账户
gooddex account balance               # 查看账户余额
gooddex account test                  # 测试账户连接
```

### 交易管理
```bash
gooddex trading list                  # 列出交易会话
gooddex trading create-session        # 创建交易会话
gooddex trading start                 # 启动交易会话
gooddex trading stop                  # 停止交易会话
gooddex trading monitor               # 监控交易会话
gooddex trading positions             # 查看持仓
```

### 数据统计
```bash
gooddex stats overview                # 交易概览
gooddex stats volume                  # 交易量统计
gooddex stats pnl                     # 盈亏统计
gooddex stats fees                    # 手续费统计
```

### 系统管理
```bash
gooddex config show                   # 显示配置
gooddex config set                    # 设置配置项
gooddex health                        # 系统健康检查
gooddex version                       # 显示版本信息
```

## ⚙️ 配置

配置文件位置: `~/.gooddex/config.toml`

```toml
[api]
base_url = "http://localhost:8000"
timeout = 30
retry_count = 3

[trading]
default_leverage = 1
max_position_size = 10.0
risk_limit = 0.02

[display]
decimal_places = 4
timezone = "UTC"
color_theme = "dark"

[logging]
level = "INFO"
file = "~/.gooddex/logs/gooddex.log"
max_size = "10MB"
backup_count = 5
```

## 🔐 安全

- API 密钥使用系统密钥环安全存储
- 支持环境变量配置敏感信息
- 内置请求签名和加密传输
- 支持双因素认证

## 📊 监控界面

```bash
# 实时监控面板
gooddex monitor dashboard

# 显示实时数据表格
┌─────────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ Session     │ Symbol   │ Status   │ PnL      │ Volume   │ Duration │
├─────────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ BTC-套利-001│ BTC/USDT │ Active   │ +$156.78 │ $50,000  │ 2h 15m   │
│ ETH-套利-002│ ETH/USDT │ Active   │ +$89.45  │ $30,000  │ 1h 45m   │
└─────────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

## 🔧 开发

### 环境设置
```bash
# 克隆仓库
git clone https://github.com/gooddex/gooddex-cli.git
cd gooddex-cli

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -e .[dev]
```

### 运行测试
```bash
pytest tests/
```

### 代码格式化
```bash
black src/
isort src/
```

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交 Pull Request 和 Issue！

## 📞 支持

- 文档: https://docs.gooddex.com/cli
- Issue: https://github.com/gooddex/gooddex-cli/issues
- 邮箱: support@gooddex.com