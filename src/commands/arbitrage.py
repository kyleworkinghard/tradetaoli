"""
自动化套利交易命令
"""

import click
import asyncio
import time
from rich.console import Console
from rich import print as rprint
from typing import Optional

from ..core.arbitrage_engine import ArbitrageEngine

console = Console()


@click.group()
def arbitrage_group():
    """🔄 自动化套利交易"""
    pass


@arbitrage_group.command()
@click.option('--symbol', '-s', required=True, help='交易对 (如: BTCUSDT)')
@click.option('--amount', '-a', required=True, type=float, help='开仓数量 (如: 0.01)')
@click.option('--leverage', '-l', default=1, type=int, help='杠杆倍数 (默认: 1)')
@click.option('--min-spread', default=1.0, type=float, help='最小价差要求 (刷量模式下忽略)')
@click.option('--account-a', required=True, type=int, help='交易所A账户ID')
@click.option('--account-b', required=True, type=int, help='交易所B账户ID')
@click.option('--strategy-version', default='v2', type=click.Choice(['v1', 'v2']), help='策略版本: v1(立即对冲) 或 v2(智能等待) (默认: v2)')
@click.option('--real-trade', is_flag=True, help='执行真实交易 (危险！)')
@click.option('--loop-count', '-c', default=1, type=int, help='循环执行次数 (默认: 1, 0表示无限循环)')
@click.option('--loop-delay', '-d', default=5, type=int, help='循环间隔秒数 (默认: 5秒)')
@click.pass_context
def execute(ctx, symbol: str, amount: float, leverage: int, min_spread: float, account_a: int, account_b: int, strategy_version: str, real_trade: bool, loop_count: int, loop_delay: int):
    """执行统一套利交易（支持任意两个交易所组合）

    策略版本说明：
    - V1: 立即对冲模式 - 一方成交后立即市价对冲另一方
    - V2: 智能等待模式 - 一方成交后智能判断价格偏移，只有向不利方向偏移>10u时才市价成交

    循环执行说明：
    - --loop-count 1: 执行1次 (默认)
    - --loop-count 5: 执行5次循环
    - --loop-count 0: 无限循环执行 (Ctrl+C停止)
    - --loop-delay: 每次循环间隔秒数
    """
    async def _execute():
        factory = None
        loop_stats = {'success': 0, 'failed': 0, 'total': 0}

        try:
            if not real_trade:
                rprint(f"[yellow]⚠️  模拟模式 - 不会进行真实交易[/yellow]")
                rprint(f"[yellow]添加 --real-trade 参数进行真实交易[/yellow]")
                return

            rprint(f"[red]⚠️  危险！这将进行真实交易！[/red]")

            # 使用交易所工厂创建统一策略
            from ..core.exchange_factory import ExchangeFactory
            factory = ExchangeFactory()

            # 验证账户组合
            exchange_a, exchange_b = factory.validate_accounts(account_a, account_b)

            # 显示配置信息
            rprint(f"[blue]🚀 启动{exchange_a.title()}+{exchange_b.title()}套利交易[/blue]")
            rprint(f"[cyan]交易对: {symbol}[/cyan]")
            rprint(f"[cyan]数量: {amount}[/cyan]")
            rprint(f"[cyan]杠杆: {leverage}x[/cyan]")
            rprint(f"[cyan]最小价差: {min_spread}[/cyan]")
            rprint(f"[cyan]策略版本: {strategy_version.upper()}[/cyan]")

            # 显示循环配置
            if loop_count == 0:
                rprint(f"[yellow]🔄 循环模式: 无限循环 (间隔{loop_delay}秒)[/yellow]")
            else:
                rprint(f"[yellow]🔄 循环模式: 执行{loop_count}次 (间隔{loop_delay}秒)[/yellow]")

            # 循环执行逻辑
            current_loop = 0

            while True:
                strategy = None
                try:
                    current_loop += 1
                    loop_stats['total'] = current_loop

                    # 显示循环进度
                    if loop_count == 0:
                        rprint(f"\n[bold blue]🚀 第{current_loop}轮循环 (无限模式)[/bold blue]")
                    else:
                        rprint(f"\n[bold blue]🚀 第{current_loop}/{loop_count}轮循环[/bold blue]")

                    # 创建新的策略实例 (每轮循环都创建新实例)
                    strategy = factory.create_arbitrage_strategy(
                        account_id_a=account_a,
                        account_id_b=account_b,
                        symbol=symbol,
                        leverage=leverage,
                        min_spread=min_spread,
                        strategy_version=strategy_version
                    )

                    # 执行套利
                    success = await strategy.execute_arbitrage(symbol, amount, real_trade)

                    if success:
                        rprint(f"[green]✅ 套利交易开始执行[/green]")
                        rprint(f"[yellow]💡 开始监控持仓状态...[/yellow]")

                        # 启动监控 (等待完成)
                        await strategy.start_monitoring()

                        # 循环结束后验证状态
                        rprint(f"[cyan]🔍 第{current_loop}轮循环结束，验证账户状态...[/cyan]")
                        verification_result = await strategy.verify_no_open_positions()

                        if verification_result:
                            loop_stats['success'] += 1
                            rprint(f"[green]🎉 第{current_loop}轮循环完成并验证通过！[/green]")
                        else:
                            loop_stats['failed'] += 1
                            rprint(f"[red]❌ 第{current_loop}轮循环完成但验证发现问题[/red]")
                            rprint(f"[red]⚠️ 建议检查账户状态后再继续[/red]")
                    else:
                        loop_stats['failed'] += 1
                        rprint(f"[red]❌ 第{current_loop}轮循环失败[/red]")

                    # 清理当前策略
                    if strategy:
                        strategy.stop_monitoring()
                        await strategy.cleanup()
                        strategy = None

                    # 检查是否继续循环
                    if loop_count > 0 and current_loop >= loop_count:
                        break

                    # 显示统计和间隔等待
                    rprint(f"[dim]📊 循环统计: 成功{loop_stats['success']}次, 失败{loop_stats['failed']}次, 总计{loop_stats['total']}次[/dim]")

                    if loop_count == 0 or current_loop < loop_count:
                        rprint(f"[dim]⏸️  等待{loop_delay}秒后开始下一轮...[/dim]")
                        await asyncio.sleep(loop_delay)

                except KeyboardInterrupt:
                    rprint(f"[yellow]⚠️  用户中断当前循环[/yellow]")
                    if strategy:
                        strategy.stop_monitoring()
                        await strategy.cleanup()
                    break
                except Exception as e:
                    loop_stats['failed'] += 1
                    rprint(f"[red]❌ 第{current_loop}轮循环异常: {e}[/red]")
                    if strategy:
                        strategy.stop_monitoring()
                        await strategy.cleanup()
                        strategy = None

                    # 异常后也等待间隔继续
                    if loop_count == 0 or current_loop < loop_count:
                        rprint(f"[dim]⏸️  等待{loop_delay}秒后开始下一轮...[/dim]")
                        await asyncio.sleep(loop_delay)

            # 显示最终统计
            rprint(f"\n[bold green]🏁 循环执行完成！[/bold green]")
            rprint(f"[cyan]📊 最终统计: 成功{loop_stats['success']}次, 失败{loop_stats['failed']}次, 总计{loop_stats['total']}次[/cyan]")

            success_rate = (loop_stats['success'] / loop_stats['total'] * 100) if loop_stats['total'] > 0 else 0
            rprint(f"[cyan]📈 成功率: {success_rate:.1f}%[/cyan]")

        except KeyboardInterrupt:
            rprint(f"[yellow]⚠️  用户中断整个循环[/yellow]")
        except Exception as e:
            rprint(f"[red]❌ 循环执行失败: {e}[/red]")
            ctx.exit(1)
        finally:
            if factory:
                await factory.cleanup_adapters()

    asyncio.run(_execute())


@arbitrage_group.command()
@click.option('--symbol', '-s', required=True, help='交易对 (如: BTCUSDT)')
@click.option('--aster-account', required=True, type=int, help='Aster账户ID')
@click.option('--okx-account', required=True, type=int, help='OKX账户ID')
@click.option('--interval', '-i', default=5, type=int, help='监控间隔 (秒)')
@click.pass_context
def monitor_spread(ctx, symbol: str, aster_account: int, okx_account: int, interval: int):
    """监控价差变化"""
    async def _monitor():
        engine = None
        try:
            rprint(f"[blue]📊 开始监控价差: {symbol}[/blue]")

            # 初始化套利引擎
            engine = ArbitrageEngine(aster_account, okx_account)
            await engine.initialize()

            while True:
                spread_1, spread_2, best_spread = await engine.get_spread(symbol)

                current_time = asyncio.get_event_loop().time()
                time_str = f"{int(current_time) % 86400 // 3600:02d}:{int(current_time) % 3600 // 60:02d}:{int(current_time) % 60:02d}"

                if spread_1 > 0:
                    direction_1 = f"[green]Aster买入→OKX卖出: +{spread_1:.2f}[/green]"
                else:
                    direction_1 = f"[red]Aster买入→OKX卖出: {spread_1:.2f}[/red]"

                if spread_2 > 0:
                    direction_2 = f"[green]OKX买入→Aster卖出: +{spread_2:.2f}[/green]"
                else:
                    direction_2 = f"[red]OKX买入→Aster卖出: {spread_2:.2f}[/red]"

                rprint(f"[dim]{time_str}[/dim] {direction_1} | {direction_2}")

                if best_spread > 1.0:
                    rprint(f"[yellow]⚡ 发现套利机会! 最大价差: {best_spread:.2f}[/yellow]")

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            rprint(f"[yellow]⚠️  监控已停止[/yellow]")
        except Exception as e:
            rprint(f"[red]❌ 监控失败: {e}[/red]")
            ctx.exit(1)
        finally:
            if engine:
                await engine.cleanup()

    asyncio.run(_monitor())


@arbitrage_group.command()
@click.option('--symbol', '-s', required=True, help='交易对 (如: BTCUSDT)')
@click.option('--account-a', required=True, type=int, help='交易所A账户ID')
@click.option('--account-b', required=True, type=int, help='交易所B账户ID')
@click.pass_context
def check_orderbook(ctx, symbol: str, account_a: int, account_b: int):
    """检查双交易所盘口深度"""
    async def _check():
        factory = None
        try:
            rprint(f"[blue]📖 检查盘口深度: {symbol}[/blue]")

            # 使用交易所工厂
            from ..core.exchange_factory import ExchangeFactory
            factory = ExchangeFactory()

            # 验证账户并创建交易所信息
            exchange_a_name, exchange_b_name = factory.validate_accounts(account_a, account_b)
            exchange_a = factory.create_exchange_info(account_a, symbol)
            exchange_b = factory.create_exchange_info(account_b, symbol)

            rprint(f"[dim]交易对格式: {exchange_a.name}={exchange_a.symbol}, {exchange_b.name}={exchange_b.symbol}[/dim]")

            # 获取盘口数据
            book_a, book_b = await asyncio.gather(
                exchange_a.adapter.get_orderbook(exchange_a.symbol, 5),
                exchange_b.adapter.get_orderbook(exchange_b.symbol, 5),
                return_exceptions=True
            )

            # 显示交易所A盘口
            if isinstance(book_a, dict) and book_a:
                rprint(f"\n[green]📊 {exchange_a.name} 盘口深度[/green]")
                rprint("[cyan]买盘 (Bids):[/cyan]")
                for i, (price, size) in enumerate(book_a.get('bids', [])[:5]):
                    rprint(f"  {i+1}. 价格: {price:.2f}, 数量: {size:.4f}")

                rprint("[cyan]卖盘 (Asks):[/cyan]")
                for i, (price, size) in enumerate(book_a.get('asks', [])[:5]):
                    rprint(f"  {i+1}. 价格: {price:.2f}, 数量: {size:.4f}")
            else:
                rprint(f"[red]❌ 获取{exchange_a.name}盘口失败: {book_a}[/red]")

            # 显示交易所B盘口
            if isinstance(book_b, dict) and book_b:
                rprint(f"\n[green]📊 {exchange_b.name} 盘口深度[/green]")
                rprint("[cyan]买盘 (Bids):[/cyan]")
                for i, (price, size) in enumerate(book_b.get('bids', [])[:5]):
                    rprint(f"  {i+1}. 价格: {price:.2f}, 数量: {size:.4f}")

                rprint("[cyan]卖盘 (Asks):[/cyan]")
                for i, (price, size) in enumerate(book_b.get('asks', [])[:5]):
                    rprint(f"  {i+1}. 价格: {price:.2f}, 数量: {size:.4f}")
            else:
                rprint(f"[red]❌ 获取{exchange_b.name}盘口失败: {book_b}[/red]")

            # 计算价差
            if (isinstance(book_a, dict) and book_a and book_a.get('bids') and book_a.get('asks') and
                isinstance(book_b, dict) and book_b and book_b.get('bids') and book_b.get('asks')):

                # 方向1: A买入 → B卖出
                spread_1 = book_b['bids'][0][0] - book_a['asks'][0][0]
                # 方向2: B买入 → A卖出
                spread_2 = book_a['bids'][0][0] - book_b['asks'][0][0]

                rprint(f"\n[yellow]💰 价差分析[/yellow]")
                rprint(f"{exchange_a.name}买入({book_a['asks'][0][0]:.2f}) → {exchange_b.name}卖出({book_b['bids'][0][0]:.2f}): {spread_1:.2f}")
                rprint(f"{exchange_b.name}买入({book_b['asks'][0][0]:.2f}) → {exchange_a.name}卖出({book_a['bids'][0][0]:.2f}): {spread_2:.2f}")

                best_spread = max(spread_1, spread_2)
                if best_spread > 1.0:
                    rprint(f"[green]✨ 发现套利机会！最佳价差: {best_spread:.2f}[/green]")

        except Exception as e:
            rprint(f"[red]❌ 检查盘口失败: {e}[/red]")
            ctx.exit(1)
        finally:
            if factory:
                await factory.cleanup_adapters()

    asyncio.run(_check())


@arbitrage_group.command()
@click.option('--symbol', '-s', required=True, help='交易对 (如: BTCUSDT)')
@click.option('--amount', '-a', required=True, type=float, help='测试数量')
@click.option('--side', required=True, type=click.Choice(['buy', 'sell']), help='交易方向')
@click.option('--exchange', required=True, type=click.Choice(['aster', 'okx']), help='交易所')
@click.option('--account-id', required=True, type=int, help='账户ID')
@click.option('--real-order', is_flag=True, help='执行真实下单 (危险！)')
@click.pass_context
def test_order(ctx, symbol: str, amount: float, side: str, exchange: str, account_id: int, real_order: bool):
    """测试下单功能"""
    async def _test():
        try:
            rprint(f"[blue]🧪 测试下单: {exchange.upper()} {side} {amount} {symbol}[/blue]")

            # 读取账户配置
            from ..core.config import get_config
            import json

            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            target_account = None
            for account in accounts:
                if account['id'] == account_id:
                    target_account = account
                    break

            if not target_account:
                raise Exception(f"未找到账户ID: {account_id}")

            # 创建适配器
            from ..core.exchange_adapters import get_exchange_adapter
            adapter = get_exchange_adapter(
                exchange=target_account['exchange'],
                api_key=target_account['api_key'],
                secret=target_account['secret_key'],
                passphrase=target_account.get('passphrase'),
                testnet=target_account.get('is_testnet', False)
            )

            # 获取当前价格
            orderbook = await adapter.get_orderbook(symbol, 1)
            if not orderbook:
                raise Exception("无法获取盘口数据")

            if side == "buy":
                price = orderbook['asks'][0][0] if orderbook['asks'] else 0
            else:
                price = orderbook['bids'][0][0] if orderbook['bids'] else 0

            rprint(f"[cyan]下单价格: {price:.2f}[/cyan]")

            if real_order:
                # 真实下单
                rprint(f"[red]⚠️  即将进行真实下单，请确认！[/red]")
                rprint(f"[yellow]按 Ctrl+C 取消，或等待3秒后自动下单...[/yellow]")

                import time
                for i in range(3, 0, -1):
                    rprint(f"[dim]{i}...[/dim]")
                    time.sleep(1)

                # 执行真实下单
                order_result = await adapter.place_order(symbol, side, amount, price, "limit")

                if order_result and order_result.get('order_id'):
                    rprint(f"[green]✅ 真实下单成功![/green]")
                    rprint(f"[green]订单ID: {order_result['order_id']}[/green]")
                    rprint(f"[green]下单价格: {order_result.get('price', price)}[/green]")
                    rprint(f"[green]下单数量: {order_result.get('amount', amount)}[/green]")
                else:
                    rprint(f"[red]❌ 下单失败[/red]")
            else:
                # 模拟模式
                import time as time_module
                rprint(f"[yellow]💡 模拟下单模式 - 不会执行真实交易[/yellow]")
                rprint(f"[green]✅ 模拟下单成功 - 如需真实下单，添加 --real-order 参数[/green]")
                rprint(f"[cyan]模拟订单ID: test_order_{int(time_module.time() * 1000)}[/cyan]")
                rprint(f"[cyan]下单价格: {price:.2f}[/cyan]")
                rprint(f"[cyan]下单数量: {amount}[/cyan]")

            if hasattr(adapter, 'close'):
                await adapter.close()

        except Exception as e:
            rprint(f"[red]❌ 测试下单失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_test())