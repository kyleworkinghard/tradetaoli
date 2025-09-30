"""
交易所工厂 - 统一创建和管理交易所适配器
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from .exchange_adapters import get_exchange_adapter
from .config import get_config
from .unified_arbitrage_strategy import ExchangeInfo


class ExchangeFactory:
    """交易所工厂类 - 统一管理交易所适配器创建"""

    def __init__(self):
        self.config = get_config()
        self.accounts_file = self.config.config_dir / "accounts.json"
        self._adapters_cache = {}

    def _convert_symbol_format(self, symbol: str, exchange: str) -> str:
        """转换交易对格式"""
        if exchange.lower() == "okx":
            # OKX永续合约使用 BTC/USDT:USDT 格式
            if '/' not in symbol:
                if symbol.endswith('USDT'):
                    base = symbol[:-4]
                    return f"{base}/USDT:USDT"  # 永续合约格式
            elif ':' not in symbol and '/' in symbol:
                return f"{symbol}:USDT"  # 添加永续合约后缀
            return symbol
        elif exchange.lower() == "backpack":
            # Backpack使用永续合约 BTC_USDC_PERP 格式
            if '/' in symbol:
                return symbol.replace('/', '_').replace('USDT', 'USDC_PERP')
            elif symbol.endswith('USDT'):
                base = symbol[:-4]  # 移除USDT
                return f"{base}_USDC_PERP"  # 添加_USDC_PERP
            elif symbol.endswith('_PERP'):
                return symbol  # 已经是正确格式
            else:
                # 如果是 BTC_USDC_PERP 格式直接返回
                return symbol
        else:
            # Aster使用 BTCUSDT 格式
            if '/' in symbol:
                return symbol.replace('/', '').replace(':USDT', '')
            return symbol

    def load_accounts(self) -> Dict[int, Dict[str, Any]]:
        """加载所有账户配置"""
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                accounts_list = json.load(f)

            # 转换为以ID为键的字典
            accounts = {}
            for account in accounts_list:
                accounts[account['id']] = account

            return accounts
        except Exception as e:
            raise Exception(f"加载账户配置失败: {e}")

    def create_exchange_info(self, account_id: int, symbol: str) -> ExchangeInfo:
        """创建交易所信息对象"""
        accounts = self.load_accounts()

        if account_id not in accounts:
            raise Exception(f"未找到账户ID: {account_id}")

        account = accounts[account_id]
        exchange_name = account['exchange'].lower()

        # 检查缓存
        cache_key = f"{exchange_name}_{account_id}"
        if cache_key in self._adapters_cache:
            adapter = self._adapters_cache[cache_key]
        else:
            # 创建适配器
            adapter = get_exchange_adapter(
                exchange=account['exchange'],
                api_key=account['api_key'],
                secret=account['secret_key'],
                passphrase=account.get('passphrase'),
                testnet=account.get('is_testnet', False)
            )
            self._adapters_cache[cache_key] = adapter

        # 转换交易对格式
        converted_symbol = self._convert_symbol_format(symbol, exchange_name)

        return ExchangeInfo(
            name=exchange_name.title(),  # Aster, Okx, Backpack
            adapter=adapter,
            symbol=converted_symbol
        )

    def create_arbitrage_strategy(self, account_id_a: int, account_id_b: int,
                                 symbol: str, leverage: int = 1,
                                 min_spread: float = 1.0, strategy_version: str = "v2"):
        """创建套利策略实例"""
        from .unified_arbitrage_strategy import UnifiedArbitrageStrategy

        # 创建两个交易所信息
        exchange_a = self.create_exchange_info(account_id_a, symbol)
        exchange_b = self.create_exchange_info(account_id_b, symbol)

        # 创建统一策略
        strategy = UnifiedArbitrageStrategy(
            exchange_a=exchange_a,
            exchange_b=exchange_b,
            leverage=leverage,
            min_spread=min_spread,
            strategy_version=strategy_version
        )

        return strategy

    def get_supported_combinations(self):
        """获取支持的交易所组合"""
        return [
            ("Aster", "Okx"),
            ("Aster", "Backpack"),
            ("Backpack", "Okx")
        ]

    def validate_accounts(self, account_id_a: int, account_id_b: int):
        """验证账户并返回交易所名称"""
        accounts = self.load_accounts()

        if account_id_a not in accounts:
            raise Exception(f"未找到账户ID: {account_id_a}")
        if account_id_b not in accounts:
            raise Exception(f"未找到账户ID: {account_id_b}")

        exchange_a = accounts[account_id_a]['exchange']
        exchange_b = accounts[account_id_b]['exchange']

        if exchange_a == exchange_b:
            raise Exception(f"不能在同一个交易所进行套利: {exchange_a}")

        return exchange_a, exchange_b

    async def cleanup_adapters(self):
        """清理所有适配器"""
        for adapter in self._adapters_cache.values():
            if hasattr(adapter, 'cleanup'):
                await adapter.cleanup()
            elif hasattr(adapter, 'close'):
                await adapter.close()

        self._adapters_cache.clear()