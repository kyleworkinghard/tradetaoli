"""
自动化套利交易引擎
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from inspect import signature
from rich.console import Console
from rich import print as rprint

from .exchange_adapters import get_exchange_adapter
from .config import get_config

console = Console()


@dataclass
class ArbitragePosition:
    """套利持仓"""
    symbol: str
    amount: float
    leverage: int
    aster_side: str  # 'buy' or 'sell'
    okx_side: str   # 'buy' or 'sell'
    backpack_side: str  # 'buy' or 'sell' (新增)
    aster_order_id: Optional[str] = None
    okx_order_id: Optional[str] = None
    backpack_order_id: Optional[str] = None  # 新增
    aster_entry_price: float = 0.0
    okx_entry_price: float = 0.0
    backpack_entry_price: float = 0.0  # 新增
    entry_spread: float = 0.0  # 开仓价差
    entry_time: Optional[datetime] = None
    status: str = "pending"  # pending, opened, closing, closed


class ArbitrageEngine:
    """自动化套利交易引擎"""

    def __init__(self, aster_account_id: int = None, okx_account_id: int = None, 
                 backpack_account_id: int = None, leverage: int = 1, min_spread: float = 1.0):
        self.aster_account_id = aster_account_id
        self.okx_account_id = okx_account_id
        self.backpack_account_id = backpack_account_id  # 新增
        self.leverage = leverage
        self.min_spread = min_spread
        self.aster_adapter = None
        self.okx_adapter = None
        self.backpack_adapter = None  # 新增
        self.positions: List[ArbitragePosition] = []
        self.running = False

    async def initialize(self):
        """初始化所有交易所适配器"""
        try:
            # 加载账户配置
            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if not accounts_file.exists():
                raise Exception("账户配置文件不存在")

            import json
            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            # 初始化Aster
            if self.aster_account_id:
                aster_account = next((acc for acc in accounts if acc["id"] == self.aster_account_id), None)
                if aster_account and aster_account["exchange"] == "aster":
                    self.aster_adapter = get_exchange_adapter(
                        exchange=aster_account['exchange'],
                        api_key=aster_account['api_key'],
                        secret=aster_account['secret_key'],
                        testnet=aster_account.get('is_testnet', False)
                    )

            # 初始化OKX
            if self.okx_account_id:
                okx_account = next((acc for acc in accounts if acc["id"] == self.okx_account_id), None)
                if okx_account and okx_account["exchange"] == "okx":
                    self.okx_adapter = get_exchange_adapter(
                        exchange=okx_account['exchange'],
                        api_key=okx_account['api_key'],
                        secret=okx_account['secret_key'],
                        passphrase=okx_account.get('passphrase'),
                        testnet=okx_account.get('is_testnet', False)
                    )

            # 初始化Backpack
            if self.backpack_account_id:
                backpack_account = next((acc for acc in accounts if acc["id"] == self.backpack_account_id), None)
                if backpack_account and backpack_account["exchange"] == "backpack":
                    self.backpack_adapter = get_exchange_adapter(
                        exchange=backpack_account['exchange'],
                        api_key=backpack_account['api_key'],
                        secret=backpack_account['secret_key'],
                        testnet=backpack_account.get('is_testnet', False)
                    )

            # 验证至少有两个适配器
            active_adapters = [adapter for adapter in [self.aster_adapter, self.okx_adapter, self.backpack_adapter] if adapter]
            if len(active_adapters) < 2:
                raise Exception("至少需要两个有效的交易所账户")

            rprint("[green]✅ 套利引擎初始化完成[/green]")

            # 显示账户信息
            if self.aster_adapter:
                rprint("Aster账户: 已连接")
            if self.okx_adapter:
                rprint("OKX账户: 已连接")
            if self.backpack_adapter:
                rprint("Backpack账户: 已连接")

        except Exception as e:
            raise Exception(f"初始化失败: {e}")

    def calculate_maker_price(self, orderbook, side, exchange="aster", spread_ratio=0.3):
        """计算Maker价格 - 支持交易所特定精度"""
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return 0.0
            
        bid_price = orderbook['bids'][0][0]
        ask_price = orderbook['asks'][0][0]
        spread = ask_price - bid_price
        
        if side == "buy":
            # 买单：在买1和卖1之间偏向买1，成为Maker
            maker_price = bid_price + (spread * spread_ratio)  # 30%位置
        else:
            # 卖单：在买1和卖1之间偏向卖1，成为Maker
            maker_price = ask_price - (spread * spread_ratio)  # 70%位置
        
        # 根据交易所调整精度
        if exchange.lower() == "aster":
            # Aster: 如果精度还有问题，可以改为整数价格
            # 备用方案：return int(maker_price)  # 整数价格
            return round(maker_price, 1)  # Aster: 1位小数
        elif exchange.lower() == "okx":
            return round(maker_price, 1)  # OKX: 1位小数
        else:
            return round(maker_price, 2)  # 默认: 2位小数

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

    async def get_spread(self, symbol: str) -> Tuple[float, float, float]:
        """获取价差信息"""
        try:
            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(symbol, "aster")
            okx_symbol = self._convert_symbol_format(symbol, "okx")

            # 并行获取两个交易所的盘口
            aster_book, okx_book = await asyncio.gather(
                self.aster_adapter.get_orderbook(aster_symbol),
                self.okx_adapter.get_orderbook(okx_symbol)
            )

            if not aster_book or not okx_book:
                return 0.0, 0.0, 0.0

            # 获取最优价格
            aster_bid = aster_book['bids'][0][0] if aster_book['bids'] else 0
            aster_ask = aster_book['asks'][0][0] if aster_book['asks'] else 0
            okx_bid = okx_book['bids'][0][0] if okx_book['bids'] else 0
            okx_ask = okx_book['asks'][0][0] if okx_book['asks'] else 0

            # 计算套利机会 (Aster买，OKX卖)
            spread_1 = okx_bid - aster_ask  # Aster买入，OKX卖出
            # 计算套利机会 (OKX买，Aster卖)
            spread_2 = aster_bid - okx_ask  # OKX买入，Aster卖出

            return spread_1, spread_2, max(spread_1, spread_2)

        except Exception as e:
            rprint(f"[red]获取价差失败: {e}[/red]")
            return 0.0, 0.0, 0.0

    async def execute_arbitrage(self, symbol: str, amount: float, leverage: int = 1, real_trade: bool = False) -> bool:
        """执行刷量交易 - 不考虑价差"""
        try:
            rprint(f"[blue]🔄 开始执行刷量交易: {symbol}[/blue]")

            # 随机选择交易方向用于刷量
            import random
            direction = random.choice(["buy_aster_sell_okx", "buy_okx_sell_aster"])

            if direction == "buy_aster_sell_okx":
                aster_side, okx_side = "buy", "sell"
            else:
                aster_side, okx_side = "sell", "buy"

            rprint(f"[cyan]📊 刷量方向: Aster{aster_side} | OKX{okx_side}[/cyan]")

            # 直接获取当前价格并下单
            return await self._place_orders(symbol, amount, aster_side, okx_side, leverage, real_trade)

        except Exception as e:
            rprint(f"[red]❌ 刷量交易失败: {e}[/red]")
            return False

    async def _place_orders(self, symbol: str, amount: float, aster_side: str, okx_side: str, leverage: int, real_trade: bool) -> bool:
        """执行下单操作"""
        try:
            # 创建持仓对象
            backpack_side = "sell" if aster_side == "buy" else "buy"  # Backpack与Aster反向
            position = ArbitragePosition(
                symbol=symbol,
                amount=amount,
                leverage=leverage,
                aster_side=aster_side,
                okx_side=okx_side,
                backpack_side=backpack_side,
                entry_time=datetime.now()
            )

            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(symbol, "aster")
            okx_symbol = self._convert_symbol_format(symbol, "okx")

            # 获取最新盘口价格
            aster_book, okx_book = await asyncio.gather(
                self.aster_adapter.get_orderbook(aster_symbol, 5),
                self.okx_adapter.get_orderbook(okx_symbol, 5)
            )

            # 计算Maker价格 (确保成为Maker而非Taker)
            aster_price = self.calculate_maker_price(aster_book, aster_side, "aster")
            okx_price = self.calculate_maker_price(okx_book, okx_side, "okx")
            
            # 验证价格有效性
            if aster_price <= 0 or okx_price <= 0:
                raise Exception("无法获取有效的Maker价格")

            rprint(f"[cyan]💰 Maker价格 - Aster: {aster_price}, OKX: {okx_price}[/cyan]")
            
            # 显示价格计算详情
            aster_bid = aster_book['bids'][0][0] if aster_book['bids'] else 0
            aster_ask = aster_book['asks'][0][0] if aster_book['asks'] else 0
            okx_bid = okx_book['bids'][0][0] if okx_book['bids'] else 0
            okx_ask = okx_book['asks'][0][0] if okx_book['asks'] else 0
            
            rprint(f"[dim]Aster盘口: 买1={aster_bid}, 卖1={aster_ask}, 价差={aster_ask-aster_bid:.2f}[/dim]")
            rprint(f"[dim]OKX盘口: 买1={okx_bid}, 卖1={okx_ask}, 价差={okx_ask-okx_bid:.2f}[/dim]")

            # 验证开单方式
            if "limit" != "limit":
                raise ValueError("开仓必须使用LIMIT订单 (Maker)")

            # 添加详细下单日志
            rprint(f"[cyan]📋 下单详情:[/cyan]")
            rprint(f"  - 下单方式: LIMIT (Maker)")
            rprint(f"  - Aster: {aster_side.upper()} {amount} BTC @ {aster_price}")
            rprint(f"  - OKX: {okx_side.upper()} {amount} BTC @ {okx_price}")
            rprint(f"  - 杠杆: {leverage}x")
            rprint(f"[green]✅ 强制LIMIT订单开仓 (Maker模式)[/green]")

            # 同时下单
            if real_trade:
                rprint("[blue]⚡ 开始同步下单...[/blue]")
                rprint("[red]⚠️  执行真实交易下单！[/red]")
                rprint(f"[cyan]设置杠杆: {leverage}x[/cyan]")
                aster_order, okx_order = await asyncio.gather(
                    self.aster_adapter.place_order(aster_symbol, aster_side, amount, aster_price, "limit", leverage),
                    self.okx_adapter.place_order(okx_symbol, okx_side, amount, okx_price, "limit", leverage),
                    return_exceptions=True
                )
            else:
                rprint("[yellow]💡 模拟下单模式 - 不会执行真实交易[/yellow]")
                # 模拟订单结果
                aster_order = {
                    "order_id": f"aster_sim_{int(time.time() * 1000)}",
                    "symbol": symbol,
                    "side": aster_side,
                    "amount": amount,
                    "price": aster_price,
                    "status": "filled"
                }
                okx_order = {
                    "order_id": f"okx_sim_{int(time.time() * 1000)}",
                    "symbol": symbol,
                    "side": okx_side,
                    "amount": amount,
                    "price": okx_price,
                    "status": "filled"
                }

            # 检查下单结果并添加成交确认日志
            if isinstance(aster_order, dict) and aster_order.get('order_id'):
                rprint(f"[green]✅ Aster下单成功: {aster_order['order_id']} (先执行)[/green]")
            else:
                rprint(f"[red]❌ Aster下单失败: {aster_order}[/red]")
                raise Exception(f"Aster下单失败: {aster_order}")

            if isinstance(okx_order, dict) and okx_order.get('order_id'):
                rprint(f"[green]✅ OKX下单成功: {okx_order['order_id']} (后执行)[/green]")
            else:
                rprint(f"[red]❌ OKX下单失败: {okx_order}[/red]")
                raise Exception(f"OKX下单失败: {okx_order}")

            position.aster_order_id = aster_order.get('order_id')
            position.okx_order_id = okx_order.get('order_id')
            position.aster_entry_price = aster_price
            position.okx_entry_price = okx_price
            position.entry_spread = abs(aster_price - okx_price)
            position.status = "opened"

            rprint(f"[green]✅ 刷量订单下单成功![/green]")
            rprint(f"[green]Aster订单ID: {position.aster_order_id}[/green]")
            rprint(f"[green]OKX订单ID: {position.okx_order_id}[/green]")
            rprint(f"[green]开仓价差: {position.entry_spread:.2f}[/green]")

            # 下单后添加风险控制成交检查
            if real_trade:
                # 🚨 立即检查下单后状态
                rprint("[cyan]🔍 检查下单后状态...[/cyan]")
                try:
                    await asyncio.sleep(0.5)  # 等待500ms让订单进入系统
                    aster_status = await self.aster_adapter.get_order_status(position.aster_order_id)
                    okx_status = await self.okx_adapter.get_order_status(position.okx_order_id)

                    if aster_status:
                        status_text = aster_status.get('status', 'unknown')
                        rprint(f"[cyan]📋 Aster订单状态: {status_text}[/cyan]")

                    if okx_status:
                        status_text = okx_status.get('status', 'unknown')
                        rprint(f"[cyan]📋 OKX订单状态: {status_text}[/cyan]")

                except Exception as e:
                    rprint(f"[yellow]⚠️ 状态检查失败: {e}[/yellow]")

                rprint("[yellow]⏳ 开始高频风险控制监控...[/yellow]")

                success = await self._check_and_handle_fills(
                    aster_order.get('order_id'),
                    okx_order.get('order_id'),
                    aster_symbol,
                    okx_symbol,
                    aster_side,
                    okx_side,
                    amount,
                    leverage
                )

                if not success:
                    rprint("[red]❌ 风险控制失败[/red]")
                    return False

                rprint("[green]✅ 风险控制完成，开始监控[/green]")

            self.positions.append(position)
            return True

        except Exception as e:
            rprint(f"[red]❌ 下单失败: {e}[/red]")
            return False

    async def _wait_for_order_fill(self, order_id, exchange, timeout=30):
        """等待订单成交"""
        for i in range(timeout):
            try:
                if exchange == "aster":
                    # 检查Aster订单状态
                    status = await self.aster_adapter.get_order_status(order_id)
                else:
                    # 检查OKX订单状态
                    status = await self.okx_adapter.get_order_status(order_id)

                if status.get('status') == 'filled':
                    rprint(f"[green]✅ {exchange.upper()}订单已成交[/green]")
                    return True
                elif status.get('status') in ['canceled', 'failed']:
                    rprint(f"[red]❌ {exchange.upper()}订单失败: {status.get('status')}[/red]")
                    return False

            except Exception as e:
                rprint(f"[yellow]⚠️ 检查{exchange}订单状态失败: {e}[/yellow]")

            await asyncio.sleep(1)  # 等待1秒后重试

        rprint(f"[red]⏰ {exchange.upper()}订单成交超时[/red]")
        return False

    def is_order_filled(self, status_dict):
        """检查订单是否已成交 - 支持多种状态格式"""
        if not isinstance(status_dict, dict):
            return False

        status = str(status_dict.get('status', '')).upper()
        filled = float(status_dict.get('filled', 0))
        amount = float(status_dict.get('amount', 0))

        # 支持的成交状态
        filled_statuses = ['FILLED', 'CLOSED', 'COMPLETE', 'COMPLETED']

        # 检查状态或完全成交
        is_status_filled = status in filled_statuses
        is_quantity_filled = (filled >= amount and amount > 0)

        return is_status_filled or is_quantity_filled

    async def _check_and_handle_fills(self, aster_order_id, okx_order_id, aster_symbol, okx_symbol, aster_side, okx_side, amount, leverage):
        """动态价格跟踪的Maker订单管理"""
        aster_filled = False
        okx_filled = False

        # 记录初始下单价格
        initial_aster_price = None
        initial_okx_price = None

        while not (aster_filled and okx_filled):  # 无超时，持续监控
            try:
                # 并发获取：订单状态 + 最新盘口
                aster_status, okx_status, aster_book, okx_book = await asyncio.gather(
                    self.aster_adapter.get_order_status(aster_order_id) if aster_order_id else asyncio.sleep(0),
                    self.okx_adapter.get_order_status(okx_order_id, okx_symbol) if okx_order_id else asyncio.sleep(0),
                    self.aster_adapter.get_orderbook(aster_symbol, 5),
                    self.okx_adapter.get_orderbook(okx_symbol, 5),
                    return_exceptions=True
                )

                # 计算当前应该的Maker价格
                current_aster_price = self.calculate_maker_price(aster_book, aster_side, "aster")
                current_okx_price = self.calculate_maker_price(okx_book, okx_side, "okx")

                # 记录初始价格
                if initial_aster_price is None:
                    initial_aster_price = current_aster_price
                    initial_okx_price = current_okx_price

                # 简化日志输出
                if isinstance(aster_status, dict):
                    print(f"📊 Aster: {aster_status.get('status')} ({aster_status.get('filled')}/{aster_status.get('amount')})")
                if isinstance(okx_status, dict):
                    print(f"📊 OKX: {okx_status.get('status')} ({okx_status.get('filled')}/{okx_status.get('amount')})")
                print(f"💹 价格: Aster={current_aster_price}, OKX={current_okx_price}")

                # 检查Aster成交情况
                if not aster_filled and self.is_order_filled(aster_status):
                    aster_filled = True
                    print("🎯 Aster订单已成交，立即处理OKX对冲")

                    # 撤销OKX订单
                    await self.okx_adapter.cancel_order(okx_order_id, okx_symbol)
                    print("🔄 OKX订单已撤销，使用MARKET方式对冲")

                    # 用市价单快速对冲
                    okx_taker_order = await self.okx_adapter.place_order(
                        okx_symbol, okx_side, amount, None, "market", leverage
                    )
                    if okx_taker_order.get('order_id'):
                        okx_filled = True
                        print("✅ OKX MARKET订单完成对冲")

                # 检查OKX成交情况
                elif not okx_filled and self.is_order_filled(okx_status):
                    okx_filled = True
                    print("🎯 OKX订单已成交，立即处理Aster对冲")

                    # 撤销Aster订单
                    await self.aster_adapter.cancel_order(aster_order_id, aster_symbol)
                    print("🔄 Aster订单已撤销，使用MARKET方式对冲")

                    # 用市价单快速对冲
                    aster_taker_order = await self.aster_adapter.place_order(
                        aster_symbol, aster_side, amount, None, "market", leverage
                    )
                    if aster_taker_order.get('order_id'):
                        aster_filled = True
                        print("✅ Aster MARKET订单完成对冲")

                # 检查Aster价格偏移 (当前only if未成交时)
                elif not aster_filled and abs(current_aster_price - initial_aster_price) > (initial_aster_price * 0.001):
                    print(f"🔄 Aster价格偏移，重新下单: {initial_aster_price} → {current_aster_price}")

                    try:
                        # 撤单
                        await self.aster_adapter.cancel_order(aster_order_id, aster_symbol)

                        # 重新下单
                        new_aster_order = await self.aster_adapter.place_order(
                            aster_symbol, aster_side, amount, current_aster_price, "limit", leverage
                        )

                        if new_aster_order.get('order_id'):
                            aster_order_id = new_aster_order.get('order_id')
                            initial_aster_price = current_aster_price
                            print(f"✅ Aster重新下单: {aster_order_id}")
                    except Exception as e:
                        print(f"❌ Aster重新下单失败: {e}")

                # 检查OKX价格偏移 (当前only if未成交时)
                elif not okx_filled and abs(current_okx_price - initial_okx_price) > (initial_okx_price * 0.001):
                    print(f"🔄 OKX价格偏移，重新下单: {initial_okx_price} → {current_okx_price}")

                    try:
                        # 撤单
                        await self.okx_adapter.cancel_order(okx_order_id, okx_symbol)

                        # 重新下单
                        new_okx_order = await self.okx_adapter.place_order(
                            okx_symbol, okx_side, amount, current_okx_price, "limit", leverage
                        )

                        if new_okx_order.get('order_id'):
                            okx_order_id = new_okx_order.get('order_id')
                            initial_okx_price = current_okx_price
                            print(f"✅ OKX重新下单: {okx_order_id}")
                    except Exception as e:
                        print(f"❌ OKX重新下单失败: {e}")

            except Exception as e:
                print(f"⚠️ 监控异常: {e}")
                # 继续监控，不要退出
                await asyncio.sleep(1)
                continue

            await asyncio.sleep(0.2)  # 每200ms检查一次，提高风险控制速度

        print("🎯 动态价格跟踪完成，双方对冲成交")
        return True

    async def _close_position_with_risk_control(self, position):
        """风险控制平仓：一方成交立即用Taker方式完成另一方"""
        try:
            rprint(f"[blue]🔄 开始风险控制平仓: {position.symbol}[/blue]")
            rprint(f"[blue]📋 平仓详情:[/blue]")
            rprint(f"  - 原开仓: Aster {position.aster_side}, OKX {position.okx_side}")

            # 反向平仓
            close_aster_side = "sell" if position.aster_side == "buy" else "buy"
            close_okx_side = "sell" if position.okx_side == "buy" else "buy"

            rprint(f"  - 平仓操作: Aster {close_aster_side}, OKX {close_okx_side}")
            rprint(f"  - 平仓方式: 风险控制模式")

            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(position.symbol, "aster")
            okx_symbol = self._convert_symbol_format(position.symbol, "okx")

            # 获取平仓价格 - 使用Maker价格
            aster_book, okx_book = await asyncio.gather(
                self.aster_adapter.get_orderbook(aster_symbol, 5),
                self.okx_adapter.get_orderbook(okx_symbol, 5)
            )

            # 计算Maker平仓价格
            aster_close_price = self.calculate_maker_price(aster_book, close_aster_side, "aster")
            okx_close_price = self.calculate_maker_price(okx_book, close_okx_side, "okx")

            # 验证平仓价格有效性
            if aster_close_price <= 0 or okx_close_price <= 0:
                raise Exception("无法获取有效的Maker平仓价格")

            rprint(f"  - 平仓价格: Aster {aster_close_price}, OKX {okx_close_price}")

            # 先尝试双方LIMIT平仓
            aster_close_order = await self.aster_adapter.place_order(aster_symbol, close_aster_side, position.amount, aster_close_price, "limit", position.leverage)
            okx_close_order = await self.okx_adapter.close_position(
                okx_symbol,
                close_okx_side,
                position.amount,
                okx_close_price,
                original_pos_side="long" if position.okx_side == "buy" else "short"
            )

            if not aster_close_order.get('order_id') or not okx_close_order.get('order_id'):
                raise Exception("平仓订单创建失败")

            # 监控平仓订单，一方成交立即处理另一方
            success = await self._check_and_handle_close_fills(
                aster_close_order.get('order_id'),
                okx_close_order.get('order_id'),
                aster_symbol,
                okx_symbol,
                close_aster_side,
                close_okx_side,
                position.amount,
                position.leverage,
                position
            )

            if success:
                position.status = "closed"
                rprint(f"[green]✅ 风险控制平仓完成[/green]")
            else:
                rprint(f"[red]❌ 风险控制平仓失败[/red]")

        except Exception as e:
            rprint(f"[red]风险控制平仓失败: {e}[/red]")

    async def _check_and_handle_close_fills(self, aster_order_id, okx_order_id, aster_symbol, okx_symbol, close_aster_side, close_okx_side, amount, leverage, position):
        """监控平仓订单，一方成交立即处理另一方"""
        aster_filled = False
        okx_filled = False

        for i in range(30):  # 30秒超时
            try:
                # 并发检查两方平仓订单状态
                aster_status, okx_status = await asyncio.gather(
                    self.aster_adapter.get_order_status(aster_order_id),
                    self.okx_adapter.get_order_status(okx_order_id, okx_symbol),  # 添加symbol参数
                    return_exceptions=True
                )

                # 简化日志输出
                if isinstance(aster_status, dict):
                    print(f"📊 平仓Aster: {aster_status.get('status')} ({aster_status.get('filled')}/{aster_status.get('amount')})")
                if isinstance(okx_status, dict):
                    print(f"📊 平仓OKX: {okx_status.get('status')} ({okx_status.get('filled')}/{okx_status.get('amount')})")

                # 检查Aster平仓成交情况
                if not aster_filled and self.is_order_filled(aster_status):
                    aster_filled = True
                    print("🎯 Aster平仓已成交，立即处理OKX平仓")

                    # 立即撤销OKX平仓订单并用Taker方式成交
                    await self.okx_adapter.cancel_order(okx_order_id, okx_symbol)
                    print("🔄 OKX平仓订单已撤销，使用MARKET方式平仓")

                    # 用市价单快速平仓
                    okx_taker_order = await self.okx_adapter.close_position(
                        okx_symbol, close_okx_side, amount, None, "long" if position.okx_side == "buy" else "short"
                    )
                    if okx_taker_order.get('order_id'):
                        okx_filled = True
                        print("✅ OKX MARKET平仓完成")

                # 检查OKX平仓成交情况
                elif not okx_filled and self.is_order_filled(okx_status):
                    okx_filled = True
                    print("🎯 OKX平仓已成交，立即处理Aster平仓")

                    # 立即撤销Aster平仓订单并用Taker方式成交
                    await self.aster_adapter.cancel_order(aster_order_id, aster_symbol)
                    print("🔄 Aster平仓订单已撤销，使用MARKET方式平仓")

                    # 用市价单快速平仓
                    aster_taker_order = await self.aster_adapter.place_order(
                        aster_symbol, close_aster_side, amount, None, "market", leverage
                    )
                    if aster_taker_order.get('order_id'):
                        aster_filled = True
                        print("✅ Aster MARKET平仓完成")

                # 双方都平仓完成
                if aster_filled and okx_filled:
                    print("🎯 双方平仓完成，风险已控制")
                    return True

            except Exception as e:
                print(f"⚠️ 检查平仓订单状态失败: {e}")

            await asyncio.sleep(1)

        # 超时处理
        print("⏰ 平仓处理超时")
        return False

    async def monitor_positions(self):
        """监控持仓 - 添加自动平仓条件"""
        while self.running:
            try:
                for position in self.positions:
                    if position.status == "opened":
                        # 检查持仓时间
                        elapsed_time = (datetime.now() - position.entry_time).total_seconds()
                        rprint(f"[blue]📊 持仓监控 - {position.symbol}[/blue]")
                        rprint(f"  - 持仓时间: {elapsed_time:.0f}秒")
                        rprint(f"  - 开仓价差: {position.entry_spread:.2f}")

                        # 获取当前价差
                        current_spread_1, current_spread_2, max_spread = await self.get_spread(position.symbol)
                        rprint(f"  - 当前价差: {max_spread:.2f}")

                        # 平仓条件1: 价差回归到开仓时的50% (优先)
                        spread_threshold = position.entry_spread * 0.5
                        if abs(max_spread) <= spread_threshold:
                            rprint(f"[yellow]📈 触发价差回归平仓条件 (当前{max_spread:.2f} <= 阈值{spread_threshold:.2f})[/yellow]")
                            await self._close_position_with_risk_control(position)
                            continue

                        # 平仓条件2: 价差扩大到开仓时的150% (止损)
                        stop_loss_threshold = position.entry_spread * 1.5
                        if abs(max_spread) >= stop_loss_threshold:
                            rprint(f"[red]🛑 触发止损平仓条件 (当前{max_spread:.2f} >= 阈值{stop_loss_threshold:.2f})[/red]")
                            await self._close_position_with_risk_control(position)
                            continue

                        # 平仓条件3: 持仓超过5分钟 (最后)
                        if elapsed_time > 300:  # 5分钟 = 300秒
                            rprint(f"[yellow]⏰ 触发定时平仓条件 (5分钟)[/yellow]")
                            await self._close_position_with_risk_control(position)
                            continue

                await asyncio.sleep(10)  # 每10秒检查一次

            except Exception as e:
                rprint(f"[red]监控持仓错误: {e}[/red]")
                await asyncio.sleep(10)

    async def auto_close_after_delay(self, delay_minutes: int = 5):
        """定时自动平仓用于刷量"""
        await asyncio.sleep(delay_minutes * 60)
        rprint(f"[yellow]⏰ {delay_minutes}分钟后自动平仓[/yellow]")
        await self._close_all_positions()

    async def _close_all_positions(self):
        """平仓所有持仓"""
        try:
            for position in self.positions:
                if position.status == "opened":
                    await self._close_position(position)
        except Exception as e:
            rprint(f"[red]批量平仓失败: {e}[/red]")

    async def _close_position(self, position: ArbitragePosition):
        """平仓 - 增强日志"""
        try:
            rprint(f"[blue]🔄 开始平仓: {position.symbol}[/blue]")
            rprint(f"[blue]📋 平仓详情:[/blue]")
            rprint(f"  - 原开仓: Aster {position.aster_side}, OKX {position.okx_side}")

            # 反向平仓
            close_aster_side = "sell" if position.aster_side == "buy" else "buy"
            close_okx_side = "sell" if position.okx_side == "buy" else "buy"

            rprint(f"  - 平仓操作: Aster {close_aster_side}, OKX {close_okx_side}")
            rprint(f"  - 平仓方式: LIMIT (Maker)")

            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(position.symbol, "aster")
            okx_symbol = self._convert_symbol_format(position.symbol, "okx")

            # 获取平仓价格 - 使用Maker价格
            aster_book, okx_book = await asyncio.gather(
                self.aster_adapter.get_orderbook(aster_symbol, 5),
                self.okx_adapter.get_orderbook(okx_symbol, 5)
            )

            # 计算Maker平仓价格
            aster_close_price = self.calculate_maker_price(aster_book, close_aster_side, "aster")
            okx_close_price = self.calculate_maker_price(okx_book, close_okx_side, "okx")
            
            # 验证平仓价格有效性
            if aster_close_price <= 0 or okx_close_price <= 0:
                raise Exception("无法获取有效的Maker平仓价格")

            # 在这里添加平仓价格日志
            rprint(f"  - 平仓价格: Aster {aster_close_price}, OKX {okx_close_price}")

            # 同时平仓 - 使用LIMIT订单(Maker)
            await asyncio.gather(
                self.aster_adapter.place_order(aster_symbol, close_aster_side, position.amount, aster_close_price, "limit", position.leverage),  # 改为limit
                self.okx_adapter.close_position(
                    okx_symbol,
                    close_okx_side,
                    position.amount,
                    okx_close_price,
                    original_pos_side="long" if position.okx_side == "buy" else "short"
                )  # 传入平仓价格和原始持仓方向
            )

            # 计算盈亏
            if position.aster_side == "buy":
                pnl = (aster_close_price - position.aster_entry_price) - (okx_close_price - position.okx_entry_price)
            else:
                pnl = (position.aster_entry_price - aster_close_price) - (position.okx_entry_price - okx_close_price)

            profit = pnl * position.amount

            position.status = "closed"

            rprint(f"[green]✅ 平仓完成[/green]")
            rprint(f"[green]📊 最终盈亏: {profit:.2f} USDT[/green]")
            rprint(f"[green]📈 平仓价格 - Aster: {aster_close_price}, OKX: {okx_close_price}[/green]")

        except Exception as e:
            rprint(f"[red]平仓失败: {e}[/red]")

    async def _close_aster_backpack_position(self, position: ArbitragePosition):
        """Aster+Backpack平仓 - 智能订单管理"""
        try:
            rprint(f"[blue]🔄 开始Aster+Backpack平仓: {position.symbol}[/blue]")

            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(position.symbol, "aster")
            backpack_symbol = self._convert_symbol_format(position.symbol, "backpack")

            # 反向平仓 (开多平空，开空平多)
            close_aster_side = "sell" if position.aster_side == "buy" else "buy"
            close_backpack_side = "sell" if position.backpack_side == "buy" else "buy"

            rprint(f"[blue]📋 平仓详情:[/blue]")
            rprint(f"  - 原开仓: Aster {position.aster_side.upper()}, Backpack {position.backpack_side.upper()}")
            rprint(f"  - 平仓操作: Aster {close_aster_side.upper()}, Backpack {close_backpack_side.upper()}")
            rprint(f"  - 平仓数量: {position.amount} BTC")

            # 获取当前盘口价格
            aster_orderbook = await self.aster_adapter.get_orderbook(aster_symbol, 5)
            backpack_orderbook = await self.backpack_adapter.get_orderbook(backpack_symbol, 5)

            if not aster_orderbook or not backpack_orderbook:
                raise Exception("无法获取平仓盘口数据")

            # 🎯 智能平仓定价 - 根据平仓方向使用正确的盘口价格
            if close_aster_side == "buy":
                aster_close_price = float(aster_orderbook["bids"][0][0])  # 买单用买一价
                rprint(f"[cyan]📈 Aster平仓买单价格: ${aster_close_price:,.2f} (买一价)[/cyan]")
            else:
                aster_close_price = float(aster_orderbook["asks"][0][0])  # 卖单用卖一价
                rprint(f"[cyan]📉 Aster平仓卖单价格: ${aster_close_price:,.2f} (卖一价)[/cyan]")

            if close_backpack_side == "buy":
                backpack_close_price = float(backpack_orderbook["bids"][0][0])  # 买单用买一价
                rprint(f"[magenta]📈 Backpack平仓买单价格: ${backpack_close_price:,.2f} (买一价)[/magenta]")
            else:
                backpack_close_price = float(backpack_orderbook["asks"][0][0])  # 卖单用卖一价
                rprint(f"[magenta]📉 Backpack平仓卖单价格: ${backpack_close_price:,.2f} (卖一价)[/magenta]")

            # 执行平仓检查和处理
            success = await self._check_and_handle_aster_backpack_close_fills(
                position, aster_symbol, backpack_symbol,
                close_aster_side, close_backpack_side,
                aster_close_price, backpack_close_price
            )

            if success:
                rprint(f"[green]✅ Aster+Backpack平仓完成[/green]")
                position.status = "closed"
            else:
                rprint(f"[red]❌ Aster+Backpack平仓失败[/red]")

            return success

        except Exception as e:
            rprint(f"[red]Aster+Backpack平仓失败: {e}[/red]")
            return False

    async def _check_and_handle_aster_backpack_close_fills(self, position, aster_symbol, backpack_symbol,
                                                          close_aster_side, close_backpack_side,
                                                          aster_close_price, backpack_close_price):
        """检查Aster+Backpack平仓订单成交并处理风险控制"""
        try:
            # 📋 同时下Aster和Backpack的限价平仓单
            rprint(f"[yellow]🔄 正在提交平仓限价订单...[/yellow]")

            aster_close_order = await self.aster_adapter.place_order(
                aster_symbol, close_aster_side, position.amount,
                aster_close_price, "limit", position.leverage
            )

            backpack_close_order = await self.backpack_adapter.place_order(
                backpack_symbol, close_backpack_side, position.amount,
                backpack_close_price, "limit"
            )

            if not aster_close_order or not backpack_close_order:
                raise Exception("平仓订单提交失败")

            aster_close_order_id = aster_close_order.get('order_id')
            backpack_close_order_id = backpack_close_order.get('order_id')

            # 💰 详细打印平仓订单内容
            rprint(f"[green]✅ 平仓限价订单提交成功![/green]")
            rprint(f"[cyan]📋 Aster平仓订单详情:[/cyan]")
            rprint(f"  订单ID: {aster_close_order_id}")
            rprint(f"  方向: {close_aster_side.upper()}")
            rprint(f"  数量: {position.amount} BTC")
            rprint(f"  价格: ${aster_close_price:,.2f}")

            rprint(f"[magenta]📋 Backpack平仓订单详情:[/magenta]")
            rprint(f"  订单ID: {backpack_close_order_id}")
            rprint(f"  方向: {close_backpack_side.upper()}")
            rprint(f"  数量: {position.amount} BTC")
            rprint(f"  价格: ${backpack_close_price:,.2f}")

            # 📊 持续监控平仓订单状态
            rprint(f"[yellow]⏰ 开始监控平仓订单状态...[/yellow]")

            last_aster_status = ""
            last_backpack_status = ""

            while True:
                await asyncio.sleep(2)

                # 🔍 检查平仓订单状态
                aster_status = await self.aster_adapter.get_order_status(aster_close_order_id)
                backpack_status = await self.backpack_adapter.get_order_status(backpack_close_order_id, backpack_symbol)

                # 状态变化时打印更新
                aster_status_str = aster_status.get('status', 'unknown') if aster_status else 'unknown'
                backpack_status_str = backpack_status.get('status', 'unknown') if backpack_status else 'unknown'

                if aster_status_str != last_aster_status:
                    if aster_status_str in ['new', 'pending', 'open']:
                        rprint(f"[cyan]⏳ Aster平仓订单等待成交[/cyan]")
                    elif aster_status_str in ['filled', 'closed']:
                        rprint(f"[green]✅ Aster平仓订单限价成交[/green]")
                    last_aster_status = aster_status_str

                if backpack_status_str != last_backpack_status:
                    if backpack_status_str in ['new', 'pending', 'open']:
                        rprint(f"[magenta]⏳ Backpack平仓订单等待成交[/magenta]")
                    elif backpack_status_str in ['filled', 'closed']:
                        rprint(f"[green]✅ Backpack平仓订单限价成交[/green]")
                    last_backpack_status = backpack_status_str

                aster_filled = self.is_order_filled(aster_status)
                backpack_filled = self.is_order_filled(backpack_status)

                if aster_filled and not backpack_filled:
                    # 🚨 Aster平仓成交，立即撤销Backpack并市价成交
                    rprint(f"[yellow]⚡ Aster平仓订单已成交，执行Backpack风险控制[/yellow]")

                    # 撤销Backpack限价单
                    rprint(f"[orange]🔄 正在撤销Backpack平仓限价单...[/orange]")
                    cancel_result = await self.backpack_adapter.cancel_order(backpack_close_order_id, backpack_symbol)
                    if cancel_result:
                        rprint(f"[orange]✅ Backpack平仓限价单撤销成功[/orange]")

                    # 市价平仓
                    rprint(f"[yellow]🚀 正在提交Backpack平仓市价单...[/yellow]")
                    market_order = await self.backpack_adapter.place_order(
                        backpack_symbol, close_backpack_side, position.amount,
                        None, "market"
                    )

                    if market_order:
                        rprint(f"[green]✅ Backpack平仓市价单提交成功[/green]")
                        rprint(f"[green]  市价单ID: {market_order.get('order_id', 'N/A')}[/green]")
                    else:
                        rprint(f"[red]❌ Backpack平仓市价单提交失败[/red]")

                    return True

                elif backpack_filled and not aster_filled:
                    # 🚨 Backpack平仓成交，立即撤销Aster并市价成交
                    rprint(f"[yellow]⚡ Backpack平仓订单已成交，执行Aster风险控制[/yellow]")

                    # 撤销Aster限价单
                    rprint(f"[cyan]🔄 正在撤销Aster平仓限价单...[/cyan]")
                    cancel_result = await self.aster_adapter.cancel_order(aster_close_order_id, aster_symbol)
                    if cancel_result:
                        rprint(f"[cyan]✅ Aster平仓限价单撤销成功[/cyan]")

                    # 市价平仓
                    rprint(f"[yellow]🚀 正在提交Aster平仓市价单...[/yellow]")
                    market_order = await self.aster_adapter.place_order(
                        aster_symbol, close_aster_side, position.amount,
                        None, "market", position.leverage
                    )

                    if market_order:
                        rprint(f"[green]✅ Aster平仓市价单提交成功[/green]")
                        rprint(f"[green]  市价单ID: {market_order.get('order_id', 'N/A')}[/green]")
                    else:
                        rprint(f"[red]❌ Aster平仓市价单提交失败[/red]")

                    return True

                elif aster_filled and backpack_filled:
                    # 🎉 双方都平仓成交，完美平仓
                    rprint(f"[green]🎉 完美！双方平仓限价单都已成交[/green]")
                    rprint(f"[green]✅ Aster平仓订单限价成交 | ✅ Backpack平仓订单限价成交[/green]")
                    return True

                # 继续监控...

        except Exception as e:
            rprint(f"[red]❌ 平仓风险控制处理失败: {e}[/red]")
            return False

    async def start_monitoring(self):
        """启动监控"""
        self.running = True
        rprint(f"[green]🚀 套利引擎启动，开始监控...[/green]")
        await self.monitor_positions()

    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        rprint(f"[yellow]⏹️ 套利引擎停止[/yellow]")

    async def cleanup(self):
        """清理资源"""
        if self.aster_adapter and hasattr(self.aster_adapter, 'close'):
            await self.aster_adapter.close()
        if self.okx_adapter and hasattr(self.okx_adapter, 'close'):
            await self.okx_adapter.close()
        if self.backpack_adapter and hasattr(self.backpack_adapter, 'close'):
            await self.backpack_adapter.close()

    # ============== 新增：Aster + Backpack 套利组合 ==============

    async def execute_aster_backpack_arbitrage(self, symbol: str, amount: float, leverage: int = 1, real_trade: bool = False) -> bool:
        """执行Aster+Backpack刷量交易"""
        try:
            if not self.aster_adapter or not self.backpack_adapter:
                raise Exception("Aster或Backpack适配器未初始化")

            rprint(f"[blue]🔄 开始执行Aster+Backpack刷量交易: {symbol}[/blue]")

            # 随机选择交易方向用于刷量
            import random
            direction = random.choice(["buy_aster_sell_backpack", "buy_backpack_sell_aster"])

            if direction == "buy_aster_sell_backpack":
                aster_side, backpack_side = "buy", "sell"
            else:
                aster_side, backpack_side = "sell", "buy"

            rprint(f"[cyan]📊 刷量方向: Aster{aster_side} | Backpack{backpack_side}[/cyan]")

            # 执行Aster+Backpack下单
            return await self._place_aster_backpack_orders(symbol, amount, aster_side, backpack_side, leverage, real_trade)

        except Exception as e:
            rprint(f"[red]❌ Aster+Backpack刷量交易失败: {e}[/red]")
            return False

    async def _place_aster_backpack_orders(self, symbol: str, amount: float, aster_side: str, backpack_side: str, leverage: int, real_trade: bool) -> bool:
        """执行Aster+Backpack下单操作"""
        try:
            # 创建持仓对象
            position = ArbitragePosition(
                symbol=symbol,
                amount=amount,
                leverage=leverage,
                aster_side=aster_side,
                okx_side="",  # 不使用OKX
                backpack_side=backpack_side,
                entry_time=datetime.now()
            )

            # 转换交易对格式
            aster_symbol = self._convert_symbol_format(symbol, "aster")
            backpack_symbol = self._convert_symbol_format(symbol, "backpack")

            # 获取盘口价格
            rprint(f"[dim]🔍 获取盘口数据: Aster={aster_symbol}, Backpack={backpack_symbol}[/dim]")

            try:
                aster_orderbook = await self.aster_adapter.get_orderbook(aster_symbol, 5)
                rprint(f"[green]✅ Aster盘口获取成功[/green]")
            except Exception as e:
                rprint(f"[red]❌ Aster盘口获取失败: {e}[/red]")
                raise Exception(f"Aster盘口获取失败: {e}")

            try:
                backpack_orderbook = await self.backpack_adapter.get_orderbook(backpack_symbol, 5)
                rprint(f"[green]✅ Backpack盘口获取成功[/green]")
            except Exception as e:
                rprint(f"[red]❌ Backpack盘口获取失败: {e}[/red]")
                raise Exception(f"Backpack盘口获取失败: {e}")

            if not aster_orderbook or not backpack_orderbook:
                raise Exception(f"盘口数据为空 - Aster: {bool(aster_orderbook)}, Backpack: {bool(backpack_orderbook)}")

            # 🎯 智能定价逻辑 - 根据开仓方向使用正确的盘口价格
            # 买单使用买一价(bid)，卖单使用卖一价(ask)
            if aster_side == "buy":
                aster_price = float(aster_orderbook["bids"][0][0])  # 买单用买一价
            else:
                aster_price = float(aster_orderbook["asks"][0][0])  # 卖单用卖一价

            if backpack_side == "buy":
                backpack_price = float(backpack_orderbook["bids"][0][0])  # 买单用买一价
            else:
                backpack_price = float(backpack_orderbook["asks"][0][0])  # 卖单用卖一价

            rprint(f"[cyan]💰 开仓价格 - Aster: ${aster_price:,.2f}, Backpack: ${backpack_price:,.2f}[/cyan]")

            position.aster_entry_price = aster_price
            position.backpack_entry_price = backpack_price
            position.entry_spread = abs(aster_price - backpack_price)

            rprint(f"[green]开仓价差: {position.entry_spread:.2f}[/green]")

            # 🚀 执行限价下单
            if real_trade:
                rprint("[blue]⚡ 开始同步下单...[/blue]")
                aster_order, backpack_order = await asyncio.gather(
                    self.aster_adapter.place_order(aster_symbol, aster_side, amount, aster_price, "limit", leverage),
                    self.backpack_adapter.place_order(backpack_symbol, backpack_side, amount, backpack_price, "limit"),
                    return_exceptions=True
                )

                # 检查下单结果
                if not isinstance(aster_order, dict) or not aster_order.get('order_id'):
                    raise Exception(f"Aster下单失败: {aster_order}")
                if not isinstance(backpack_order, dict) or not backpack_order.get('order_id'):
                    raise Exception(f"Backpack下单失败: {backpack_order}")

                position.aster_order_id = aster_order.get('order_id')
                position.backpack_order_id = backpack_order.get('order_id')

                rprint(f"[green]✅ 限价订单提交成功![/green]")
                rprint(f"[green]Aster订单ID: {position.aster_order_id}[/green]")
                rprint(f"[green]Backpack订单ID: {position.backpack_order_id}[/green]")

                # 🚨 立即检查下单后状态
                rprint("[cyan]🔍 检查下单后状态...[/cyan]")
                try:
                    await asyncio.sleep(0.5)  # 等待500ms让订单进入系统
                    aster_status = await self.aster_adapter.get_order_status(position.aster_order_id)
                    backpack_status = await self.backpack_adapter.get_order_status(position.backpack_order_id, backpack_symbol)

                    if aster_status:
                        status_text = aster_status.get('status', 'unknown')
                        rprint(f"[cyan]📋 Aster订单状态: {status_text}[/cyan]")

                    if backpack_status:
                        status_text = backpack_status.get('status', 'unknown')
                        rprint(f"[cyan]📋 Backpack订单状态: {status_text}[/cyan]")

                except Exception as e:
                    rprint(f"[yellow]⚠️ 状态检查失败: {e}[/yellow]")

            # 下单后添加风险控制成交检查
            if real_trade:
                rprint("[yellow]⏳ 开始高频风险控制监控...[/yellow]")

                # 使用通用的成交检查逻辑
                success = await self._check_and_handle_universal_fills(
                    position.aster_order_id,
                    position.backpack_order_id,
                    aster_symbol,
                    backpack_symbol,
                    position.aster_side,
                    position.backpack_side,
                    position.amount,
                    position.leverage,
                    self.aster_adapter,
                    self.backpack_adapter
                )

                if success:
                    self.positions.append(position)
                    position.status = "opened"
                    rprint(f"[green]✅ Aster+Backpack套利持仓开启成功[/green]")
                else:
                    rprint(f"[red]❌ Aster+Backpack套利失败[/red]")

                return success
            else:
                rprint(f"[blue]🧪 模拟交易完成[/blue]")
                return True

        except Exception as e:
            rprint(f"[red]❌ 下单失败: {e}[/red]")
            return False

    async def _check_and_handle_universal_fills(self, exchange_a_order_id, exchange_b_order_id, exchange_a_symbol, exchange_b_symbol,
                                           exchange_a_side, exchange_b_side, amount, leverage, exchange_a_adapter, exchange_b_adapter) -> bool:
        """通用的成交检查逻辑 - 基于成熟的Aster+OKX策略"""
        exchange_a_filled = False
        exchange_b_filled = False

        check_count = 0
        while not (exchange_a_filled and exchange_b_filled):
            try:
                await asyncio.sleep(0.2)  # 200ms高频检查，降低风险窗口
                check_count += 1

                # 获取订单状态
                exchange_a_status = await exchange_a_adapter.get_order_status(exchange_a_order_id)
                # Backpack需要symbol参数，其他交易所不需要
                if exchange_b_adapter.__class__.__name__ == 'BackpackAdapter':
                    exchange_b_status = await exchange_b_adapter.get_order_status(exchange_b_order_id, exchange_b_symbol)
                else:
                    exchange_b_status = await exchange_b_adapter.get_order_status(exchange_b_order_id)

                # 每5次检查(1秒)显示一次状态，避免刷屏
                if check_count % 5 == 0:
                    if isinstance(exchange_a_status, dict):
                        status_a = exchange_a_status.get('status', 'unknown')
                        if status_a in ['new', 'pending', 'open'] and not exchange_a_filled:
                            print(f"⏳ {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}等待成交 (检查{check_count}次)")

                    if isinstance(exchange_b_status, dict):
                        status_b = exchange_b_status.get('status', 'unknown')
                        if status_b in ['new', 'pending', 'open'] and not exchange_b_filled:
                            print(f"⏳ {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}等待成交 (检查{check_count}次)")

                # 立即反馈成交状态
                if isinstance(exchange_a_status, dict):
                    status_a = exchange_a_status.get('status', 'unknown')
                    if status_a in ['filled', 'closed'] and not exchange_a_filled:
                        print(f"🎯 {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}订单成交! (检查{check_count}次)")

                if isinstance(exchange_b_status, dict):
                    status_b = exchange_b_status.get('status', 'unknown')
                    if status_b in ['filled', 'closed'] and not exchange_b_filled:
                        print(f"🎯 {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}订单成交! (检查{check_count}次)")

                # 🚨 关键风险控制：检查成交情况并立即对冲
                if not exchange_a_filled and self.is_order_filled(exchange_a_status):
                    exchange_a_filled = True
                    print(f"🚨 {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}已成交！立即撤单并市价对冲{exchange_b_adapter.__class__.__name__.replace('Adapter', '')}")

                    try:
                        # 撤销Exchange B订单
                        if exchange_b_adapter.__class__.__name__ == 'BackpackAdapter':
                            cancel_result = await exchange_b_adapter.cancel_order(exchange_b_order_id, exchange_b_symbol)
                        else:
                            cancel_result = await exchange_b_adapter.cancel_order(exchange_b_order_id)
                        print(f"✅ {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}订单撤销成功")

                        # 立即市价单对冲
                        if exchange_b_adapter.__class__.__name__ == 'AsterAdapter':
                            # Aster需要leverage参数
                            market_order = await exchange_b_adapter.place_order(exchange_b_symbol, exchange_b_side, amount, None, "market", leverage)
                        elif exchange_b_adapter.__class__.__name__ == 'BackpackAdapter':
                            # Backpack市价单
                            market_order = await exchange_b_adapter.place_order(exchange_b_symbol, exchange_b_side, amount, None, "market")
                        else:
                            # OKX等其他交易所
                            market_order = await exchange_b_adapter.place_order(exchange_b_symbol, exchange_b_side, amount, None, "market")

                        if market_order and market_order.get('order_id'):
                            exchange_b_filled = True
                            print(f"🎯 {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}市价单对冲完成！订单ID: {market_order.get('order_id')}")
                        else:
                            print(f"❌ {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}市价单对冲失败！")

                    except Exception as hedge_error:
                        print(f"❌ 对冲失败: {hedge_error}")

                elif not exchange_b_filled and self.is_order_filled(exchange_b_status):
                    exchange_b_filled = True
                    print(f"🚨 {exchange_b_adapter.__class__.__name__.replace('Adapter', '')}已成交！立即撤单并市价对冲{exchange_a_adapter.__class__.__name__.replace('Adapter', '')}")

                    try:
                        # 撤销Exchange A订单
                        if exchange_a_adapter.__class__.__name__ == 'BackpackAdapter':
                            cancel_result = await exchange_a_adapter.cancel_order(exchange_a_order_id, exchange_a_symbol)
                        else:
                            cancel_result = await exchange_a_adapter.cancel_order(exchange_a_order_id)
                        print(f"✅ {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}订单撤销成功")

                        # 立即市价单对冲
                        if exchange_a_adapter.__class__.__name__ == 'AsterAdapter':
                            # Aster需要leverage参数
                            market_order = await exchange_a_adapter.place_order(exchange_a_symbol, exchange_a_side, amount, None, "market", leverage)
                        elif exchange_a_adapter.__class__.__name__ == 'BackpackAdapter':
                            # Backpack市价单
                            market_order = await exchange_a_adapter.place_order(exchange_a_symbol, exchange_a_side, amount, None, "market")
                        else:
                            # OKX等其他交易所
                            market_order = await exchange_a_adapter.place_order(exchange_a_symbol, exchange_a_side, amount, None, "market")

                        if market_order and market_order.get('order_id'):
                            exchange_a_filled = True
                            print(f"🎯 {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}市价单对冲完成！订单ID: {market_order.get('order_id')}")
                        else:
                            print(f"❌ {exchange_a_adapter.__class__.__name__.replace('Adapter', '')}市价单对冲失败！")

                    except Exception as hedge_error:
                        print(f"❌ 对冲失败: {hedge_error}")

            except Exception as e:
                print(f"❌ 检查订单状态失败: {e}")
                await asyncio.sleep(1)

        print("✅ 双方订单处理完成")
        return True

    # ============== 新增：Backpack + OKX 套利组合 ==============

    async def execute_backpack_okx_arbitrage(self, symbol: str, amount: float, leverage: int = 1, real_trade: bool = False) -> bool:
        """执行Backpack+OKX刷量交易"""
        try:
            if not self.backpack_adapter or not self.okx_adapter:
                raise Exception("Backpack或OKX适配器未初始化")

            rprint(f"[blue]🔄 开始执行Backpack+OKX刷量交易: {symbol}[/blue]")

            # 随机选择交易方向用于刷量
            import random
            direction = random.choice(["buy_backpack_sell_okx", "buy_okx_sell_backpack"])

            if direction == "buy_backpack_sell_okx":
                backpack_side, okx_side = "buy", "sell"
            else:
                backpack_side, okx_side = "sell", "buy"

            rprint(f"[cyan]📊 刷量方向: Backpack{backpack_side} | OKX{okx_side}[/cyan]")

            # 执行Backpack+OKX下单
            return await self._place_backpack_okx_orders(symbol, amount, backpack_side, okx_side, leverage, real_trade)

        except Exception as e:
            rprint(f"[red]❌ Backpack+OKX刷量交易失败: {e}[/red]")
            return False

    async def _place_backpack_okx_orders(self, symbol: str, amount: float, backpack_side: str, okx_side: str, leverage: int, real_trade: bool) -> bool:
        """执行Backpack+OKX下单操作"""
        try:
            # 创建持仓对象
            position = ArbitragePosition(
                symbol=symbol,
                amount=amount,
                leverage=leverage,
                aster_side="",  # 不使用Aster
                okx_side=okx_side,
                backpack_side=backpack_side,
                entry_time=datetime.now()
            )

            # 转换交易对格式
            backpack_symbol = self._convert_symbol_format(symbol, "backpack")
            okx_symbol = self._convert_symbol_format(symbol, "okx")

            # 获取盘口价格
            backpack_orderbook = await self.backpack_adapter.get_orderbook(backpack_symbol, 5)
            okx_orderbook = await self.okx_adapter.get_orderbook(okx_symbol, 5)

            if not backpack_orderbook or not okx_orderbook:
                raise Exception("无法获取盘口数据")

            # 计算下单价格 (使用maker价格)
            backpack_price = float(backpack_orderbook["asks"][0][0]) if backpack_side == "buy" else float(backpack_orderbook["bids"][0][0])
            okx_price = float(okx_orderbook["asks"][0][0]) if okx_side == "buy" else float(okx_orderbook["bids"][0][0])

            position.backpack_entry_price = backpack_price
            position.okx_entry_price = okx_price
            position.entry_spread = abs(backpack_price - okx_price)

            rprint(f"[green]开仓价差: {position.entry_spread:.2f}[/green]")

            # 下单后添加风险控制成交检查
            if real_trade:
                rprint("[yellow]⏳ 开始风险控制监控...[/yellow]")

                success = await self._check_and_handle_backpack_okx_fills(
                    position,
                    backpack_symbol,
                    okx_symbol,
                    real_trade
                )

                if success:
                    self.positions.append(position)
                    position.status = "opened"
                    rprint(f"[green]✅ Backpack+OKX套利持仓开启成功[/green]")
                else:
                    rprint(f"[red]❌ Backpack+OKX套利失败[/red]")

                return success
            else:
                rprint(f"[blue]🧪 模拟交易完成[/blue]")
                return True

        except Exception as e:
            rprint(f"[red]❌ 下单失败: {e}[/red]")
            return False

    async def _check_and_handle_backpack_okx_fills(self, position: ArbitragePosition, backpack_symbol: str, okx_symbol: str, real_trade: bool) -> bool:
        """检查Backpack+OKX订单成交并处理风险控制"""
        try:
            # 同时下Backpack和OKX的limit订单
            backpack_order = await self.backpack_adapter.place_order(
                backpack_symbol, position.backpack_side, position.amount,
                position.backpack_entry_price, "limit"
            )

            okx_order = await self.okx_adapter.place_order(
                okx_symbol, position.okx_side, position.amount,
                position.okx_entry_price, "limit", position.leverage
            )

            if not backpack_order or not okx_order:
                raise Exception("下单失败")

            position.backpack_order_id = backpack_order.get('order_id')
            position.okx_order_id = okx_order.get('order_id')

            rprint(f"[green]📋 订单已提交:[/green]")
            rprint(f"  Backpack: {position.backpack_order_id}")
            rprint(f"  OKX: {position.okx_order_id}")

            # 持续监控直到至少一方成交
            while True:
                await asyncio.sleep(1)

                # 检查订单状态
                backpack_status = await self.backpack_adapter.get_order_status(position.backpack_order_id, backpack_symbol)
                okx_status = await self.okx_adapter.get_order_status(position.okx_order_id, okx_symbol)

                backpack_filled = self.is_order_filled(backpack_status)
                okx_filled = self.is_order_filled(okx_status)

                if backpack_filled and not okx_filled:
                    # Backpack成交，立即撤销OKX并市价成交
                    rprint(f"[yellow]⚡ Backpack成交，执行OKX风险控制[/yellow]")
                    await self.okx_adapter.cancel_order(position.okx_order_id, okx_symbol)

                    market_order = await self.okx_adapter.place_order(
                        okx_symbol, position.okx_side, position.amount,
                        None, "market", position.leverage
                    )
                    rprint(f"[green]✅ OKX市价单已执行[/green]")
                    return True

                elif okx_filled and not backpack_filled:
                    # OKX成交，立即撤销Backpack并市价成交
                    rprint(f"[yellow]⚡ OKX成交，执行Backpack风险控制[/yellow]")
                    await self.backpack_adapter.cancel_order(position.backpack_order_id, backpack_symbol)

                    market_order = await self.backpack_adapter.place_order(
                        backpack_symbol, position.backpack_side, position.amount,
                        None, "market"
                    )
                    rprint(f"[green]✅ Backpack市价单已执行[/green]")
                    return True

                elif backpack_filled and okx_filled:
                    # 双方都成交
                    rprint(f"[green]✅ 双方都已成交[/green]")
                    return True

                # 继续监控...

        except Exception as e:
            rprint(f"[red]❌ 风险控制处理失败: {e}[/red]")
            return False