"""
统一套利策略 - 干净的V1版本
支持任意两个交易所之间的套利交易
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from rich.console import Console
from rich import print as rprint

console = Console()

@dataclass
class ExchangeInfo:
    """交易所信息"""
    name: str
    adapter: Any
    symbol: str

@dataclass
class ArbitragePosition:
    """套利持仓"""
    symbol: str
    amount: float
    leverage: int
    exchange_a: Any
    exchange_b: Any
    side_a: str  # buy/sell
    side_b: str  # buy/sell
    entry_price_a: float
    entry_price_b: float
    entry_spread: float
    entry_time: datetime
    order_id_a: str = None
    order_id_b: str = None
    status: str = "pending"

class UnifiedArbitrageStrategy:
    """统一套利策略引擎"""

    def __init__(self, exchange_a, exchange_b, leverage: int = 1, min_spread: float = 0.0, strategy_version: str = "v1"):
        self.exchange_a = exchange_a
        self.exchange_b = exchange_b
        self.leverage = leverage
        self.min_spread = min_spread
        self.strategy_version = strategy_version
        self.positions: List[ArbitragePosition] = []
        self.monitoring_active = False

        # 高频盘口缓存
        self._orderbook_cache_a = None
        self._orderbook_cache_b = None
        self._cache_time_a = 0
        self._cache_time_b = 0
        self._cache_ttl = 0.05  # 50ms缓存有效期

        rprint(f"[green]🔗 使用统一套利策略: {exchange_a.name}+{exchange_b.name}[/green]")

    async def _check_account_balance(self, amount: float) -> bool:
        """检查账户余额和保证金是否足够"""
        try:
            # 检查两个交易所的账户状态
            balance_a_ok = await self._check_single_exchange_balance(self.exchange_a, amount)
            balance_b_ok = await self._check_single_exchange_balance(self.exchange_b, amount)

            if balance_a_ok and balance_b_ok:
                rprint(f"[green]✅ 账户余额检查通过[/green]")
                return True
            else:
                if not balance_a_ok:
                    rprint(f"[yellow]⚠️ {self.exchange_a.name}账户余额不足[/yellow]")
                if not balance_b_ok:
                    rprint(f"[yellow]⚠️ {self.exchange_b.name}账户余额不足[/yellow]")
                return False

        except Exception as e:
            rprint(f"[yellow]⚠️ 余额检查失败: {e}[/yellow]")
            return True  # 检查失败时允许继续，避免过度谨慎

    async def _check_single_exchange_balance(self, exchange, amount: float) -> bool:
        """检查单个交易所的余额"""
        try:
            if exchange.name.lower() == 'aster':
                # Aster交易所余额检查
                balance = await exchange.adapter.get_balance()
                if balance and 'USDT' in balance:
                    usdt_balance = float(balance['USDT'].get('free', 0))
                    required_margin = amount * 115000  # 估算需要的保证金（BTC价格约115000）
                    return usdt_balance > required_margin

            elif exchange.name.lower() == 'backpack':
                # Backpack交易所余额检查
                balance = await exchange.adapter.get_balance()
                if balance and isinstance(balance, list):
                    usdc_balance = 0
                    for asset in balance:
                        if asset.get('symbol') == 'USDC':
                            usdc_balance = float(asset.get('available', 0))
                            break

                    required_margin = amount * 115000  # 估算需要的保证金
                    return usdc_balance > required_margin

            return True  # 无法检查时默认允许

        except Exception as e:
            rprint(f"[yellow]⚠️ {exchange.name}余额检查异常: {e}[/yellow]")
            return True  # 异常时默认允许继续

    async def _get_fresh_orderbook(self, exchange, force_refresh: bool = False) -> Dict:
        """获取新鲜的盘口数据（带缓存）"""
        try:
            current_time = time.time()

            if exchange == self.exchange_a:
                cache_key = 'a'
                if (not force_refresh and
                    self._orderbook_cache_a and
                    current_time - self._cache_time_a < self._cache_ttl):
                    return self._orderbook_cache_a

                book = await exchange.adapter.get_orderbook(exchange.symbol, 5)
                self._orderbook_cache_a = book
                self._cache_time_a = current_time
                return book

            else:  # exchange_b
                cache_key = 'b'
                if (not force_refresh and
                    self._orderbook_cache_b and
                    current_time - self._cache_time_b < self._cache_ttl):
                    return self._orderbook_cache_b

                book = await exchange.adapter.get_orderbook(exchange.symbol, 5)
                self._orderbook_cache_b = book
                self._cache_time_b = current_time
                return book

        except Exception as e:
            rprint(f"[red]❌ 获取{exchange.name}盘口失败: {e}[/red]")
            return None

    async def _update_orderbook_cache_parallel(self):
        """并行更新双方交易所盘口缓存"""
        try:
            # 并行获取双方盘口数据
            tasks = [
                self._get_fresh_orderbook(self.exchange_a, force_refresh=True),
                self._get_fresh_orderbook(self.exchange_b, force_refresh=True)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            # 静默处理，不影响主要流程
            pass

    async def _get_smart_order_price(self, exchange, side: str, order_type: str) -> float:
        """根据新定义获取智能下单价格"""
        try:
            book = await self._get_fresh_orderbook(exchange)
            if not book or not book.get("bids") or not book.get("asks"):
                raise Exception(f"无效盘口数据")

            bid_price = float(book["bids"][0][0])  # 买一价
            ask_price = float(book["asks"][0][0])  # 卖一价

            if order_type == "limit":  # 限价单 (Maker)
                if side == "buy":
                    return bid_price  # 多单用买单价
                else:  # sell
                    return ask_price  # 空单用卖单价
            else:  # market (Taker)
                if side == "buy":
                    return ask_price  # 多单用卖单价（立即成交）
                else:  # sell
                    return bid_price  # 空单用买单价（立即成交）

        except Exception as e:
            rprint(f"[red]❌ 获取{exchange.name}智能价格失败: {e}[/red]")
            return None

    async def get_spread(self, symbol: str) -> Tuple[float, float, float]:
        """获取双向价差"""
        try:
            # 并行获取两个交易所的盘口数据
            book_a, book_b = await asyncio.gather(
                self.exchange_a.adapter.get_orderbook(self.exchange_a.symbol, 5),
                self.exchange_b.adapter.get_orderbook(self.exchange_b.symbol, 5)
            )

            if not book_a or not book_b:
                raise Exception("无法获取盘口数据")

            # 计算两个方向的价差
            # 方向1: A买入 -> B卖出
            price_a_buy = float(book_a["asks"][0][0])  # A的卖一价（买入成本）
            price_b_sell = float(book_b["bids"][0][0])  # B的买一价（卖出收入）
            spread_1 = price_b_sell - price_a_buy

            # 方向2: B买入 -> A卖出
            price_b_buy = float(book_b["asks"][0][0])  # B的卖一价（买入成本）
            price_a_sell = float(book_a["bids"][0][0])  # A的买一价（卖出收入）
            spread_2 = price_a_sell - price_b_buy

            best_spread = max(spread_1, spread_2)

            return spread_1, spread_2, best_spread

        except Exception as e:
            rprint(f"[red]❌ 获取价差失败: {e}[/red]")
            return 0.0, 0.0, 0.0

    def determine_trading_direction(self, spread_1: float, spread_2: float) -> Tuple[str, str]:
        """确定交易方向"""
        if abs(spread_1) < self.min_spread and abs(spread_2) < self.min_spread:
            # 刷量模式：随机选择方向
            import random
            return random.choice([("buy", "sell"), ("sell", "buy")])

        if spread_1 > spread_2:
            return ("buy", "sell")  # A买入，B卖出
        else:
            return ("sell", "buy")  # A卖出，B买入

    async def execute_arbitrage(self, symbol: str, amount: float, real_trade: bool = False) -> bool:
        """执行套利交易"""
        try:
            rprint(f"[blue]🔄 开始执行{self.exchange_a.name}+{self.exchange_b.name}套利交易: {symbol}[/blue]")


            # 获取价差信息
            spread_1, spread_2, best_spread = await self.get_spread(symbol)

            # 确定交易方向
            side_a, side_b = self.determine_trading_direction(spread_1, spread_2)

            rprint(f"[cyan]📊 交易方向: {self.exchange_a.name}{side_a} | {self.exchange_b.name}{side_b}[/cyan]")

            # 获取盘口价格
            rprint(f"[dim]🔍 获取盘口数据...[/dim]")

            book_a = await self.exchange_a.adapter.get_orderbook(self.exchange_a.symbol, 5)
            book_b = await self.exchange_b.adapter.get_orderbook(self.exchange_b.symbol, 5)

            if not book_a or not book_b:
                raise Exception("无法获取盘口数据")

            # 传统定价方式 - 使用买一/卖一价挂单
            if side_a == "buy":
                price_a = float(book_a["bids"][0][0])  # 买单用买一价
            else:
                price_a = float(book_a["asks"][0][0])  # 卖单用卖一价

            if side_b == "buy":
                price_b = float(book_b["bids"][0][0])  # 买单用买一价
            else:
                price_b = float(book_b["asks"][0][0])  # 卖单用卖一价

            rprint(f"[cyan]💰 开仓价格 - {self.exchange_a.name}: ${price_a:,.2f}, {self.exchange_b.name}: ${price_b:,.2f}[/cyan]")

            entry_spread = abs(price_a - price_b)
            rprint(f"[green]开仓价差: {entry_spread:.2f}[/green]")

            # 创建持仓对象
            position = ArbitragePosition(
                symbol=symbol,
                amount=amount,
                leverage=self.leverage,
                exchange_a=self.exchange_a,
                exchange_b=self.exchange_b,
                side_a=side_a,
                side_b=side_b,
                entry_price_a=price_a,
                entry_price_b=price_b,
                entry_spread=entry_spread,
                entry_time=datetime.now()
            )

            if real_trade:
                # 根据新定义使用智能限价下单
                rprint("[blue]⚡ 开始同步智能限价下单...[/blue]")
                order_a = await self._place_limit_order(
                    self.exchange_a, side_a, amount
                )
                order_b = await self._place_limit_order(
                    self.exchange_b, side_b, amount
                )

                # 检查下单结果
                if not order_a or not order_a.get('order_id'):
                    raise Exception(f"{self.exchange_a.name}下单失败: {order_a}")
                if not order_b or not order_b.get('order_id'):
                    raise Exception(f"{self.exchange_b.name}下单失败: {order_b}")

                position.order_id_a = order_a.get('order_id')
                position.order_id_b = order_b.get('order_id')

                rprint(f"[green]✅ 限价订单提交成功![/green]")
                rprint(f"[green]{self.exchange_a.name}订单ID: {position.order_id_a}[/green]")
                rprint(f"[green]{self.exchange_b.name}订单ID: {position.order_id_b}[/green]")

                # 立即检查下单后状态
                await self._check_initial_order_status(position)

                # 启动V1风险控制监控
                rprint("[yellow]⏳ 开始V1高频风险控制监控...[/yellow]")

                success = await self._monitor_and_hedge(position)

                if success:
                    self.positions.append(position)
                    position.status = "opened"
                    rprint(f"[green]✅ {self.exchange_a.name}+{self.exchange_b.name}套利持仓开启成功[/green]")
                else:
                    rprint(f"[red]❌ {self.exchange_a.name}+{self.exchange_b.name}套利失败[/red]")

                return success
            else:
                rprint(f"[blue]🧪 模拟交易完成[/blue]")
                return True

        except Exception as e:
            rprint(f"[red]❌ 套利执行失败: {e}[/red]")
            return False

    async def _place_limit_order(self, exchange, side: str, amount: float) -> Dict:
        """下限价单 - 使用新定义的智能价格"""
        try:
            # 获取限价单价格（Maker价格）
            price = await self._get_smart_order_price(exchange, side, "limit")
            if not price:
                raise Exception("获取限价单价格失败")

            rprint(f"[cyan]📋 {exchange.name} {side} 限价单价格: ${price:,.2f}[/cyan]")

            # 根据交易所名称调用不同的API
            if exchange.name.lower() == 'aster':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'backpack':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'okx':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            else:
                # 默认API调用
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit"
                )
        except Exception as e:
            rprint(f"[red]❌ {exchange.name}限价单失败: {e}[/red]")
            return None

    async def _place_order_for_exchange(self, exchange, side: str, amount: float, price: float = None) -> Dict:
        """根据交易所特性下单（兼容旧方法）"""
        try:
            if price is None:
                # 如果没有提供价格，使用限价单逻辑
                return await self._place_limit_order(exchange, side, amount)

            # 根据交易所名称调用不同的API
            if exchange.name.lower() == 'aster':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'backpack':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'okx':
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            else:
                # 默认API调用
                return await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit"
                )
        except Exception as e:
            rprint(f"[red]❌ {exchange.name}下单失败: {e}[/red]")
            return None

    async def _check_initial_order_status(self, position: ArbitragePosition):
        """检查下单后初始状态"""
        rprint("[cyan]🔍 检查下单后状态...[/cyan]")
        try:
            await asyncio.sleep(0.5)  # 等待500ms让订单进入系统

            status_a = await self._get_order_status(position.exchange_a, position.order_id_a)
            status_b = await self._get_order_status(position.exchange_b, position.order_id_b)

            if status_a:
                status_text = status_a.get('status', 'unknown')
                rprint(f"[cyan]📋 {position.exchange_a.name}订单状态: {status_text}[/cyan]")

            if status_b:
                status_text = status_b.get('status', 'unknown')
                rprint(f"[cyan]📋 {position.exchange_b.name}订单状态: {status_text}[/cyan]")

        except Exception as e:
            rprint(f"[yellow]⚠️ 状态检查失败: {e}[/yellow]")

    async def _get_order_status(self, exchange, order_id: str) -> Dict:
        """获取订单状态"""
        try:
            if exchange.name.lower() == 'aster':
                return await exchange.adapter.get_order_status(order_id, exchange.symbol)
            elif exchange.name.lower() == 'backpack':
                return await exchange.adapter.get_order_status(order_id, exchange.symbol)
            elif exchange.name.lower() == 'okx':
                return await exchange.adapter.get_order_status(order_id, exchange.symbol)
            else:
                return await exchange.adapter.get_order_status(order_id)
        except Exception as e:
            rprint(f"[red]❌ 获取{exchange.name}订单状态失败: {e}[/red]")
            return None

    async def _cancel_order(self, exchange, order_id: str) -> bool:
        """撤销订单"""
        try:
            if exchange.name.lower() in ['aster', 'backpack']:
                # Aster和Backpack需要symbol参数
                return await exchange.adapter.cancel_order(order_id, exchange.symbol)
            else:
                # OKX等其他交易所不需要symbol参数
                return await exchange.adapter.cancel_order(order_id)
        except Exception as e:
            rprint(f"[red]❌ 撤销{exchange.name}订单失败: {e}[/red]")
            return False

    def _is_order_filled(self, order_status: Dict) -> bool:
        """判断订单是否成交"""
        if not order_status:
            return False

        status = order_status.get('status', '').lower()
        return status in ['filled', 'closed', 'executed']

    async def _monitor_and_hedge(self, position: ArbitragePosition) -> bool:
        """V1策略：立即对冲监控"""
        filled_a = False
        filled_b = False
        check_count = 0

        rprint(f"[blue]🚀 V1策略启动：立即对冲模式[/blue]")

        # 持续监控双方订单状态
        while not (filled_a and filled_b):
            try:
                await asyncio.sleep(0.1)  # 100ms超高频检查
                check_count += 1

                # 1. 高频更新盘口缓存 (确保市价对冲时使用最新价格)
                await self._update_orderbook_cache_parallel()

                # 2. 检查订单状态
                status_a = await self._get_order_status(position.exchange_a, position.order_id_a)
                status_b = await self._get_order_status(position.exchange_b, position.order_id_b)

                # V1立即对冲：检测到成交就立即执行，不等待任何循环
                if status_a and self._is_order_filled(status_a) and not filled_a:
                    filled_a = True
                    rprint(f"[red]🚨 {position.exchange_a.name}已成交！V1立即撤单市价对冲{position.exchange_b.name}[/red]")

                    if not filled_b:
                        await self._cancel_order(position.exchange_b, position.order_id_b)
                        # 获取市价对冲时的实际价格
                        market_price = await self._get_smart_order_price(position.exchange_b, position.side_b, "market")
                        market_order = await self._place_market_order(position.exchange_b, position.side_b, position.amount)
                        if market_order:
                            filled_b = True
                            # 记录实际市价对冲价格
                            position._actual_price_b = market_price
                            rprint(f"[green]🎯 {position.exchange_b.name}V1市价对冲完成！[/green]")
                        break

                elif status_b and self._is_order_filled(status_b) and not filled_b:
                    filled_b = True
                    rprint(f"[red]🚨 {position.exchange_b.name}已成交！V1立即撤单市价对冲{position.exchange_a.name}[/red]")

                    if not filled_a:
                        await self._cancel_order(position.exchange_a, position.order_id_a)
                        # 获取市价对冲时的实际价格
                        market_price = await self._get_smart_order_price(position.exchange_a, position.side_a, "market")
                        market_order = await self._place_market_order(position.exchange_a, position.side_a, position.amount)
                        if market_order:
                            filled_a = True
                            # 记录实际市价对冲价格
                            position._actual_price_a = market_price
                            rprint(f"[green]🎯 {position.exchange_a.name}V1市价对冲完成！[/green]")
                        break

                # 每50次检查输出一次状态日志（因为频率提高了一倍）
                if check_count % 50 == 0:
                    rprint(f"[dim]📊 V1监控进行中...({check_count*0.1:.1f}s) 双方订单待成交[/dim]")

                # 超时保护
                if check_count > 600:  # 60秒超时（100ms*600=60s）
                    rprint(f"[yellow]⏰ V1监控超时(60s)，强制结束[/yellow]")
                    return False

            except Exception as e:
                rprint(f"[red]❌ V1监控异常: {e}[/red]")
                await asyncio.sleep(1)

        # V1对冲完成后，更新实际成交价格
        await self._update_actual_entry_prices(position)
        return True

    async def _update_actual_entry_prices(self, position: ArbitragePosition):
        """更新实际成交价格（用于准确计算价差）"""
        try:
            rprint(f"[cyan]🔍 更新实际成交价格...[/cyan]")

            # 对于V1策略，实际成交价就是下单时的价格
            # 因为限价单成交价格就是限价价格，市价单我们用的是实时盘口价

            # 检查是否有存储的实际成交价（市价对冲时设置）
            actual_price_a = getattr(position, '_actual_price_a', position.entry_price_a)
            actual_price_b = getattr(position, '_actual_price_b', position.entry_price_b)

            rprint(f"[green]📊 {position.exchange_a.name}实际成交价: ${actual_price_a:,.2f}[/green]")
            rprint(f"[green]📊 {position.exchange_b.name}实际成交价: ${actual_price_b:,.2f}[/green]")

            # 更新持仓的实际价格和价差
            position.entry_price_a = actual_price_a
            position.entry_price_b = actual_price_b
            position.entry_spread = abs(actual_price_a - actual_price_b)

            rprint(f"[blue]📈 实际开仓价差: {position.entry_spread:.2f}[/blue]")

        except Exception as e:
            rprint(f"[yellow]⚠️ 更新实际成交价格失败: {e}[/yellow]")

    async def _get_order_execution_info(self, exchange, order_id: str) -> Dict:
        """获取订单成交信息（包含实际成交价格）"""
        try:
            # 先获取订单状态
            status = await self._get_order_status(exchange, order_id)
            if not status:
                return None

            # 如果订单已成交，获取成交详情
            if self._is_order_filled(status):
                # 调试：打印订单状态数据
                rprint(f"[cyan]🔍 调试{exchange.name}订单状态数据: {status}[/cyan]")

                # 尝试获取成交价格
                if 'average_price' in status and status['average_price']:
                    price = float(status['average_price'])
                    rprint(f"[green]✅ 使用average_price: ${price:,.2f}[/green]")
                    return {"execution_price": price}
                elif 'avg_price' in status and status['avg_price']:
                    price = float(status['avg_price'])
                    rprint(f"[green]✅ 使用avg_price: ${price:,.2f}[/green]")
                    return {"execution_price": price}
                elif 'price' in status and status['price']:
                    price = float(status['price'])
                    rprint(f"[yellow]⚠️ 使用订单价格price(可能非成交价): ${price:,.2f}[/yellow]")
                    return {"execution_price": price}
                elif 'filled_price' in status and status['filled_price']:
                    price = float(status['filled_price'])
                    rprint(f"[green]✅ 使用filled_price: ${price:,.2f}[/green]")
                    return {"execution_price": price}
                else:
                    # 如果没有成交价，使用当前市价作为估计
                    rprint(f"[red]❌ 未找到成交价格字段，使用市价估算[/red]")
                    book = await exchange.adapter.get_orderbook(exchange.symbol, 1)
                    mid_price = (float(book["bids"][0][0]) + float(book["asks"][0][0])) / 2
                    rprint(f"[yellow]📊 使用市价中间价估算: ${mid_price:,.2f}[/yellow]")
                    return {"execution_price": mid_price}

            return None
        except Exception as e:
            rprint(f"[yellow]⚠️ 获取{exchange.name}订单执行信息失败: {e}[/yellow]")
            return None

    async def _place_market_order(self, exchange, side: str, amount: float) -> Dict:
        """穿透式市价单 - 确保立即成交"""
        try:
            # 获取最新盘口数据
            book = await self._get_fresh_orderbook(exchange, force_refresh=True)
            if not book or not book.get("bids") or not book.get("asks"):
                raise Exception("无法获取盘口数据")

            # 穿透式定价策略 - 使用更深层价格确保成交
            if side == "buy":
                # 买单：使用卖5价格（穿透式）
                if len(book["asks"]) >= 5:
                    price = float(book["asks"][4][0])  # 卖5价
                else:
                    price = float(book["asks"][-1][0])  # 最深卖价
                    price *= 1.001  # 额外加0.1%确保成交
            else:  # sell
                # 卖单：使用买5价格（穿透式）
                if len(book["bids"]) >= 5:
                    price = float(book["bids"][4][0])  # 买5价
                else:
                    price = float(book["bids"][-1][0])  # 最深买价
                    price *= 0.999  # 额外减0.1%确保成交

            rprint(f"[yellow]⚡ 穿透式市价对冲: {exchange.name} {side} {amount} @${price:,.2f}[/yellow]")

            # 下单 - 使用穿透式限价单确保成交
            if exchange.name.lower() == 'aster':
                order = await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'backpack':
                order = await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            elif exchange.name.lower() == 'okx':
                order = await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit", self.leverage
                )
            else:
                order = await exchange.adapter.place_order(
                    exchange.symbol, side, amount, price, "limit"
                )

            # 验证订单成交（最多等待3秒）
            if order:
                order_id = order.get('id') or order.get('order_id')
                if order_id:
                    await self._verify_order_fill(exchange, order_id, max_wait_time=3.0)

            return order

        except Exception as e:
            rprint(f"[red]❌ {exchange.name}穿透式市价单失败: {e}[/red]")
            return None

    async def _verify_order_fill(self, exchange, order_id: str, max_wait_time: float = 3.0):
        """验证订单成交"""
        try:
            start_time = time.time()
            check_interval = 0.2  # 200ms检查间隔

            while time.time() - start_time < max_wait_time:
                status = await self._get_order_status(exchange, order_id)
                if status and self._is_order_filled(status):
                    rprint(f"[green]✅ {exchange.name}穿透式订单成交确认[/green]")
                    return True
                await asyncio.sleep(check_interval)

            rprint(f"[yellow]⚠️ {exchange.name}穿透式订单未在{max_wait_time}s内完全成交[/yellow]")
            return False

        except Exception as e:
            rprint(f"[yellow]⚠️ 验证{exchange.name}订单成交失败: {e}[/yellow]")
            return False

    async def start_monitoring(self):
        """启动持仓监控"""
        self.monitoring_active = True
        rprint("[blue]🚀 统一套利监控启动[/blue]")

        while self.monitoring_active:
            try:
                if not self.positions:
                    await asyncio.sleep(10)
                    continue

                # 检查是否还有活跃持仓
                active_positions = [pos for pos in self.positions if pos.status == "opened"]
                if not active_positions:
                    rprint("[green]🏁 所有持仓已平仓，监控结束[/green]")
                    self.monitoring_active = False
                    break

                for position in active_positions:
                    # 检查持仓时间和价差变化
                    await self._check_position_status(position)

                await asyncio.sleep(0.5)  # 避免过于频繁的检查

            except Exception as e:
                rprint(f"[red]❌ 监控异常: {e}[/red]")
                await asyncio.sleep(5)

    async def _check_position_status(self, position: ArbitragePosition):
        """检查持仓状态"""
        try:
            # 获取当前价差
            spread_1, spread_2, current_spread = await self.get_spread(position.symbol)

            # 持仓时间
            position_time = (datetime.now() - position.entry_time).total_seconds()

            rprint(f"[dim]📊 持仓监控: {position.exchange_a.name}+{position.exchange_b.name}, "
                  f"时间{position_time:.0f}s, 当前价差{current_spread:.2f}[/dim]")

            # 简单的平仓逻辑：持仓超过5分钟或价差回归
            should_close = False
            if position_time > 300:  # 5分钟
                should_close = True
                rprint(f"[yellow]⏰ 持仓时间过长，准备平仓[/yellow]")
            elif current_spread < position.entry_spread * 0.5:  # 价差回归50%
                should_close = True
                rprint(f"[green]📈 价差回归，准备平仓[/green]")

            if should_close:
                await self._close_position(position)

        except Exception as e:
            rprint(f"[red]❌ 检查持仓状态失败: {e}[/red]")

    async def _close_position(self, position: ArbitragePosition):
        """平仓 - 使用与开仓一致的限价+市价逻辑"""
        try:
            rprint(f"[blue]🔄 开始平仓: {position.exchange_a.name}+{position.exchange_b.name}[/blue]")

            # 反向操作
            close_side_a = "sell" if position.side_a == "buy" else "buy"
            close_side_b = "sell" if position.side_b == "buy" else "buy"

            # 先同步下智能限价单
            rprint(f"[cyan]⚡ 开始同步智能限价平仓...[/cyan]")
            close_order_a = await self._place_limit_order(position.exchange_a, close_side_a, position.amount)
            close_order_b = await self._place_limit_order(position.exchange_b, close_side_b, position.amount)

            if not close_order_a or not close_order_b:
                rprint(f"[red]❌ 平仓限价单下单失败[/red]")
                return

            close_order_id_a = close_order_a.get('id') or close_order_a.get('order_id')
            close_order_id_b = close_order_b.get('id') or close_order_b.get('order_id')

            rprint(f"[green]✅ 平仓限价单提交成功![/green]")
            rprint(f"{position.exchange_a.name}平仓订单ID: {close_order_id_a}")
            rprint(f"{position.exchange_b.name}平仓订单ID: {close_order_id_b}")

            # V1平仓监控：一方成交立即市价对冲另一方
            await self._monitor_close_and_hedge(position, close_order_id_a, close_order_id_b, close_side_a, close_side_b)

        except Exception as e:
            rprint(f"[red]❌ 平仓异常: {e}[/red]")

    async def _monitor_close_and_hedge(self, position: ArbitragePosition, close_order_id_a: str, close_order_id_b: str, close_side_a: str, close_side_b: str):
        """监控平仓订单并进行对冲"""
        try:
            filled_a = False
            filled_b = False
            check_count = 0

            rprint(f"[blue]🚀 平仓V1策略启动：立即对冲模式[/blue]")

            # 持续监控双方平仓订单状态
            while not (filled_a and filled_b):
                try:
                    await asyncio.sleep(0.1)  # 100ms超高频检查
                    check_count += 1

                    # 检查平仓订单状态
                    status_a = await self._get_order_status(position.exchange_a, close_order_id_a)
                    status_b = await self._get_order_status(position.exchange_b, close_order_id_b)

                    # V1立即对冲：检测到成交就立即执行
                    if status_a and self._is_order_filled(status_a) and not filled_a:
                        filled_a = True
                        rprint(f"[red]🚨 {position.exchange_a.name}平仓已成交！V1立即撤单市价对冲{position.exchange_b.name}[/red]")

                        if not filled_b:
                            await self._cancel_order(position.exchange_b, close_order_id_b)
                            market_order = await self._place_market_order(position.exchange_b, close_side_b, position.amount)
                            if market_order:
                                filled_b = True
                                rprint(f"[green]🎯 {position.exchange_b.name}平仓市价对冲完成！[/green]")
                            break

                    elif status_b and self._is_order_filled(status_b) and not filled_b:
                        filled_b = True
                        rprint(f"[red]🚨 {position.exchange_b.name}平仓已成交！V1立即撤单市价对冲{position.exchange_a.name}[/red]")

                        if not filled_a:
                            await self._cancel_order(position.exchange_a, close_order_id_a)
                            market_order = await self._place_market_order(position.exchange_a, close_side_a, position.amount)
                            if market_order:
                                filled_a = True
                                rprint(f"[green]🎯 {position.exchange_a.name}平仓市价对冲完成！[/green]")
                            break

                    # 每50次检查输出一次状态日志
                    if check_count % 50 == 0:
                        rprint(f"[dim]📊 平仓V1监控进行中...({check_count*0.1:.1f}s) 双方平仓订单待成交[/dim]")

                    # 超时保护
                    if check_count > 600:  # 60秒超时
                        rprint(f"[yellow]⏰ 平仓V1监控超时(60s)，强制结束[/yellow]")
                        return False

                except Exception as e:
                    rprint(f"[red]❌ 平仓V1监控异常: {e}[/red]")

            if filled_a and filled_b:
                position.status = "closed"
                rprint(f"[green]✅ 平仓完成[/green]")
                return True

        except Exception as e:
            rprint(f"[red]❌ 平仓监控异常: {e}[/red]")
            return False

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring_active = False
        rprint("[yellow]⏹️ 套利监控停止[/yellow]")


    async def verify_no_open_positions(self):
        """简单验证是否有未平仓持仓和订单"""
        try:
            # 检查A交易所
            result_a = await self._check_exchange_clean(self.exchange_a)
            # 检查B交易所
            result_b = await self._check_exchange_clean(self.exchange_b)

            if result_a and result_b:
                rprint(f"[green]✅ 循环结束验证通过[/green]")
                return True
            else:
                rprint(f"[red]❌ 发现未处理持仓或订单[/red]")
                return False

        except Exception as e:
            rprint(f"[red]❌ 验证失败: {e}[/red]")
            return False

    async def _check_exchange_clean(self, exchange):
        """简单检查交易所是否干净"""
        try:
            # 检查持仓
            try:
                positions = await exchange.adapter.get_positions()
                if positions:
                    open_positions = [pos for pos in positions if pos.get('contracts', 0) != 0 or pos.get('size', 0) != 0]
                    if open_positions:
                        return False
            except:
                pass

            # 检查订单
            try:
                orders = await exchange.adapter.get_open_orders()
                if orders:
                    return False
            except:
                pass

            return True

        except:
            return False

    async def cleanup(self):
        """清理资源"""
        self.stop_monitoring()
        rprint("[red]🧹 资源清理完成[/red]")