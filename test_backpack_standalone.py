#!/usr/bin/env python3
"""
独立测试Backpack交易所API功能
测试：账户余额、订单历史、永续合约下单
"""

import asyncio
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from src.core.backpack_adapter import BackpackAdapter

console = Console()


async def test_backpack_balance(adapter: BackpackAdapter):
    """测试账户余额查询"""
    try:
        rprint("[blue]🔍 测试Backpack账户余额查询...[/blue]")

        # 获取账户余额
        balances = await adapter.get_balance()

        if balances:
            rprint(f"[green]✅ 成功获取余额数据，共 {len(balances)} 个币种[/green]")

            # 创建余额表格
            table = Table(title="💰 Backpack账户余额")
            table.add_column("币种", style="cyan")
            table.add_column("可用余额", justify="right", style="green")
            table.add_column("冻结余额", justify="right", style="yellow")
            table.add_column("总余额", justify="right", style="white")

            for balance in balances:
                table.add_row(
                    balance["currency"],
                    f"{balance['free_balance']:.8f}",
                    f"{balance['used_balance']:.8f}",
                    f"{balance['total_balance']:.8f}"
                )

            console.print(table)
        else:
            rprint("[yellow]⚠️ 未获取到余额数据或余额为空[/yellow]")

        return True

    except Exception as e:
        rprint(f"[red]❌ 余额查询失败: {e}[/red]")
        return False


async def test_backpack_order_history(adapter: BackpackAdapter):
    """测试订单历史查询"""
    try:
        rprint("[blue]🔍 测试Backpack订单历史查询...[/blue]")

        # 获取订单历史
        orders = await adapter.get_order_history(limit=10)

        if orders:
            rprint(f"[green]✅ 成功获取订单历史，共 {len(orders)} 个订单[/green]")

            # 创建订单表格
            table = Table(title="📋 Backpack订单历史")
            table.add_column("订单ID", style="cyan")
            table.add_column("交易对", style="blue")
            table.add_column("方向", style="yellow")
            table.add_column("数量", justify="right", style="green")
            table.add_column("价格", justify="right", style="magenta")
            table.add_column("状态", style="white")

            for order in orders[:10]:  # 只显示前10个
                order_id = str(order.get("id", ""))[:8] + "..."
                symbol = order.get("symbol", "")
                side = order.get("side", "").upper()
                quantity = order.get("quantity", 0)
                price = order.get("price", 0)
                status = order.get("status", "").upper()

                table.add_row(order_id, symbol, side, f"{quantity}", f"{price}", status)

            console.print(table)
        else:
            rprint("[yellow]⚠️ 未获取到订单历史或历史为空[/yellow]")

        # 获取成交历史
        rprint("[blue]🔍 测试Backpack成交历史查询...[/blue]")
        fills = await adapter.get_fill_history(limit=5)

        if fills:
            rprint(f"[green]✅ 成功获取成交历史，共 {len(fills)} 笔成交[/green]")

            # 创建成交表格
            table = Table(title="💸 Backpack成交历史")
            table.add_column("成交ID", style="cyan")
            table.add_column("交易对", style="blue")
            table.add_column("方向", style="yellow")
            table.add_column("成交量", justify="right", style="green")
            table.add_column("成交价", justify="right", style="magenta")
            table.add_column("手续费", justify="right", style="red")

            for fill in fills[:5]:  # 只显示前5个
                fill_id = str(fill.get("id", ""))[:8] + "..."
                symbol = fill.get("symbol", "")
                side = fill.get("side", "").upper()
                quantity = fill.get("quantity", 0)
                price = fill.get("price", 0)
                fee = fill.get("fee", 0)

                table.add_row(fill_id, symbol, side, f"{quantity}", f"{price}", f"{fee}")

            console.print(table)
        else:
            rprint("[yellow]⚠️ 未获取到成交历史或历史为空[/yellow]")

        return True

    except Exception as e:
        rprint(f"[red]❌ 订单历史查询失败: {e}[/red]")
        return False


async def test_backpack_place_order(adapter: BackpackAdapter):
    """测试永续合约下单"""
    try:
        rprint("[blue]🔍 测试Backpack永续合约下单...[/blue]")

        # 先获取BTC永续合约的当前价格
        symbol = "BTC_USDC_PERP"

        rprint(f"[cyan]1. 获取 {symbol} 当前价格...[/cyan]")
        ticker = await adapter.get_ticker(symbol)
        if ticker:
            last_price = float(ticker.get('lastPrice', 0))
            rprint(f"[green]当前价格: ${last_price:,.2f}[/green]")
        else:
            rprint("[red]❌ 无法获取当前价格[/red]")
            return False

        rprint(f"[cyan]2. 获取 {symbol} 盘口深度...[/cyan]")
        orderbook = await adapter.get_orderbook(symbol, 5)
        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
            rprint(f"[green]最优买价: ${best_bid:,.2f}, 最优卖价: ${best_ask:,.2f}[/green]")
            rprint(f"[yellow]价差: ${best_ask - best_bid:,.2f} ({(best_ask - best_bid)/best_ask*100:.3f}%)[/yellow]")
        else:
            rprint("[red]❌ 无法获取盘口数据[/red]")
            return False

        # 测试限价买单 (低于市价5%)
        test_price = last_price * 0.95
        test_amount = 0.001  # 测试少量

        rprint(f"[cyan]3. 测试限价买单...[/cyan]")
        rprint(f"[yellow]⚠️ 这是真实下单测试！[/yellow]")
        rprint(f"交易对: {symbol}")
        rprint(f"方向: BUY")
        rprint(f"数量: {test_amount} BTC")
        rprint(f"价格: ${test_price:,.2f}")

        # 用户确认
        rprint(f"[red]⚠️ 这将执行真实的限价买单！[/red]")
        rprint(f"[red]如果你的Backpack账户有真实资金，这将产生实际交易！[/red]")
        rprint(f"[yellow]继续将在3秒后执行...[/yellow]")

        import time
        for i in range(3, 0, -1):
            rprint(f"[dim]{i}...[/dim]")
            time.sleep(1)

        # 执行下单
        order_result = await adapter.place_order(
            symbol=symbol,
            side="buy",
            amount=test_amount,
            price=test_price,
            order_type="limit"
        )

        if order_result and order_result.get('order_id'):
            rprint(f"[green]✅ 限价买单成功![/green]")
            rprint(f"[green]订单ID: {order_result['order_id']}[/green]")
            rprint(f"[green]状态: {order_result.get('status', 'unknown')}[/green]")

            # 等待片刻后查询订单状态
            rprint(f"[cyan]4. 查询订单状态...[/cyan]")
            await asyncio.sleep(2)

            order_status = await adapter.get_order_status(order_result['order_id'], symbol)
            if order_status:
                rprint(f"[blue]订单状态: {order_status.get('status', 'unknown')}[/blue]")
                rprint(f"[blue]成交数量: {order_status.get('filled', 0)}[/blue]")
                rprint(f"[blue]剩余数量: {order_status.get('remaining', 0)}[/blue]")

            # 如果订单未完全成交，尝试撤销
            if order_status.get('status') in ['new', 'partiallyFilled']:
                rprint(f"[cyan]5. 撤销测试订单...[/cyan]")
                cancel_result = await adapter.cancel_order(order_result['order_id'], symbol)
                if cancel_result:
                    rprint(f"[green]✅ 订单撤销成功[/green]")
                else:
                    rprint(f"[red]❌ 订单撤销失败[/red]")

        else:
            rprint(f"[red]❌ 限价买单失败[/red]")
            return False

        return True

    except Exception as e:
        rprint(f"[red]❌ 下单测试失败: {e}[/red]")
        return False


async def main():
    """主测试函数"""
    try:
        rprint("[bold blue]🚀 Backpack交易所API独立测试[/bold blue]")

        # 加载账户配置
        config_dir = Path.home() / ".gooddex"
        accounts_file = config_dir / "accounts.json"

        if not accounts_file.exists():
            rprint("[red]❌ 未找到账户配置文件[/red]")
            return

        with open(accounts_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)

        # 查找Backpack账户
        backpack_account = None
        for account in accounts:
            if account.get('exchange') == 'backpack':
                backpack_account = account
                break

        if not backpack_account:
            rprint("[red]❌ 未找到Backpack账户配置[/red]")
            return

        rprint(f"[green]✅ 找到Backpack账户: {backpack_account['name']}[/green]")

        # 创建Backpack适配器
        adapter = BackpackAdapter(
            api_key=backpack_account['api_key'],
            secret_key=backpack_account['secret_key'],
            testnet=backpack_account.get('testnet', False)
        )

        # 测试连接
        rprint("[cyan]📡 测试连接...[/cyan]")
        connection_result = await adapter.test_connection()

        if connection_result.get('success'):
            rprint(f"[green]✅ {connection_result['message']}[/green]")
        else:
            rprint(f"[red]❌ 连接失败: {connection_result['message']}[/red]")
            return

        rprint("\n" + "="*60 + "\n")

        # 执行测试
        tests = [
            ("账户余额查询", test_backpack_balance),
            ("订单历史查询", test_backpack_order_history),
            ("永续合约下单", test_backpack_place_order)
        ]

        results = []
        for test_name, test_func in tests:
            rprint(f"[bold cyan]🧪 开始测试: {test_name}[/bold cyan]")
            result = await test_func(adapter)
            results.append((test_name, result))
            rprint(f"[{'green' if result else 'red'}]{'✅' if result else '❌'} {test_name}: {'通过' if result else '失败'}[/{'green' if result else 'red'}]")
            rprint("\n" + "-"*60 + "\n")

        # 汇总结果
        rprint("[bold blue]📊 测试结果汇总[/bold blue]")
        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            color = "green" if result else "red"
            rprint(f"[{color}]{status}[/{color}] {test_name}")

        rprint(f"\n[bold {'green' if passed == total else 'yellow'}]总计: {passed}/{total} 项测试通过[/bold {'green' if passed == total else 'yellow'}]")

        # 清理会话
        if hasattr(adapter, 'session') and adapter.session:
            await adapter.session.aclose()

    except Exception as e:
        rprint(f"[red]❌ 测试执行失败: {e}[/red]")


if __name__ == "__main__":
    asyncio.run(main())