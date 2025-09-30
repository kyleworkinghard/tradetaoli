#!/usr/bin/env python3
"""
Backpack API功能演示
展示公开API功能和私有API接口结构
"""

import asyncio
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from src.core.backpack_adapter import BackpackAdapter

console = Console()


async def demo_public_apis():
    """演示公开API功能（无需认证）"""
    rprint("[bold blue]📡 Backpack公开API功能演示[/bold blue]")

    # 使用dummy credentials创建适配器（仅用于公开API）
    adapter = BackpackAdapter(
        api_key="demo_key",
        secret_key="ZGVtb19zZWNyZXRfa2V5X2Zvcl9wdWJsaWNfYXBpc19vbmx5",  # Base64 encoded dummy
        testnet=False
    )

    try:
        # 1. 测试服务器连接
        rprint("[cyan]1. 测试服务器连接...[/cyan]")
        server_time = await adapter.get_time()
        rprint(f"[green]✅ 服务器时间: {server_time}[/green]")

        # 2. 获取系统状态
        rprint("[cyan]2. 获取系统状态...[/cyan]")
        status = await adapter.get_status()
        rprint(f"[green]✅ 系统状态: {status}[/green]")

        # 3. 获取所有市场
        rprint("[cyan]3. 获取支持的市场...[/cyan]")
        markets = await adapter.get_markets()
        if markets:
            rprint(f"[green]✅ 共支持 {len(markets)} 个交易市场[/green]")

            # 显示永续合约市场
            perp_markets = [m for m in markets if 'PERP' in m.get('symbol', '')]
            if perp_markets:
                table = Table(title="💱 永续合约市场")
                table.add_column("交易对", style="cyan")
                table.add_column("基础币种", style="blue")
                table.add_column("计价币种", style="yellow")
                table.add_column("状态", style="green")

                for market in perp_markets[:10]:  # 显示前10个
                    table.add_row(
                        market.get("symbol", ""),
                        market.get("baseCurrency", ""),
                        market.get("quoteCurrency", ""),
                        market.get("status", "")
                    )

                console.print(table)

        # 4. 获取BTC永续合约行情
        rprint("[cyan]4. 获取BTC永续合约行情...[/cyan]")
        symbol = "BTC_USDC_PERP"
        ticker = await adapter.get_ticker(symbol)
        if ticker:
            rprint(f"[green]✅ {symbol} 行情数据:[/green]")
            rprint(f"  最新价格: ${float(ticker.get('lastPrice', 0)):,.2f}")
            rprint(f"  24h涨跌: {float(ticker.get('priceChange', 0)):+.2f}")
            rprint(f"  24h涨跌幅: {float(ticker.get('priceChangePercent', 0)):+.2f}%")
            rprint(f"  24h成交量: {float(ticker.get('volume', 0)):,.2f}")

        # 5. 获取盘口深度
        rprint("[cyan]5. 获取盘口深度...[/cyan]")
        orderbook = await adapter.get_orderbook(symbol, 5)
        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
            rprint(f"[green]✅ {symbol} 盘口深度:[/green]")

            # 买盘表格
            table = Table(title="📈 买盘 (Bids)")
            table.add_column("价格", justify="right", style="green")
            table.add_column("数量", justify="right", style="white")

            for price, size in orderbook['bids'][:5]:
                table.add_row(f"${price:,.2f}", f"{size:.4f}")

            console.print(table)

            # 卖盘表格
            table = Table(title="📉 卖盘 (Asks)")
            table.add_column("价格", justify="right", style="red")
            table.add_column("数量", justify="right", style="white")

            for price, size in orderbook['asks'][:5]:
                table.add_row(f"${price:,.2f}", f"{size:.4f}")

            console.print(table)

            # 价差分析
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
            spread = best_ask - best_bid
            spread_pct = spread / best_ask * 100

            rprint(f"[yellow]💰 价差分析:[/yellow]")
            rprint(f"  最优买价: ${best_bid:,.2f}")
            rprint(f"  最优卖价: ${best_ask:,.2f}")
            rprint(f"  价差: ${spread:,.2f} ({spread_pct:.3f}%)")

        # 6. 获取最近成交
        rprint("[cyan]6. 获取最近成交记录...[/cyan]")
        recent_trades = await adapter.get_recent_trades(symbol, 5)
        if recent_trades:
            rprint(f"[green]✅ 最近 {len(recent_trades)} 笔成交:[/green]")

            table = Table(title="💸 最近成交")
            table.add_column("时间", style="dim")
            table.add_column("价格", justify="right", style="cyan")
            table.add_column("数量", justify="right", style="yellow")
            table.add_column("方向", style="green")

            for trade in recent_trades:
                timestamp = trade.get('timestamp', 0)
                if timestamp:
                    import datetime
                    time_str = datetime.datetime.fromtimestamp(timestamp / 1000).strftime("%H:%M:%S")
                else:
                    time_str = "N/A"

                price = float(trade.get('price', 0))
                quantity = float(trade.get('quantity', 0))
                side = "买入" if trade.get('side') == 'Buy' else "卖出"

                table.add_row(time_str, f"${price:,.2f}", f"{quantity:.4f}", side)

            console.print(table)

        rprint(f"[green]✅ 公开API功能演示完成[/green]")

    except Exception as e:
        rprint(f"[red]❌ 公开API测试失败: {e}[/red]")
    finally:
        # 清理会话
        if hasattr(adapter, 'session') and adapter.session:
            await adapter.session.aclose()


async def demo_private_api_interfaces():
    """演示私有API接口结构（需要有效的Ed25519密钥）"""
    rprint("[bold blue]🔒 Backpack私有API接口演示[/bold blue]")

    rprint("[yellow]⚠️ 以下为私有API接口说明，需要有效的Ed25519密钥对[/yellow]")

    # 接口说明
    interfaces = [
        {
            "function": "get_balance()",
            "description": "获取账户余额",
            "endpoint": "GET /api/v1/capital",
            "action": "balanceQuery",
            "returns": "List[Dict] - 各币种余额信息"
        },
        {
            "function": "get_order_history(symbol, limit, offset)",
            "description": "获取订单历史",
            "endpoint": "GET /api/v1/orders/history",
            "action": "orderHistoryQueryAll",
            "returns": "List[Dict] - 历史订单列表"
        },
        {
            "function": "get_fill_history(symbol, limit, offset)",
            "description": "获取成交历史",
            "endpoint": "GET /api/v1/fills",
            "action": "fillHistoryQueryAll",
            "returns": "List[Dict] - 历史成交列表"
        },
        {
            "function": "place_order(symbol, side, amount, price, order_type)",
            "description": "下单（永续合约）",
            "endpoint": "POST /api/v1/order",
            "action": "orderExecute",
            "returns": "Dict - 订单确认信息"
        },
        {
            "function": "get_positions()",
            "description": "获取持仓信息",
            "endpoint": "GET /api/v1/position",
            "action": "positionQuery",
            "returns": "List[Dict] - 持仓列表"
        },
        {
            "function": "cancel_order(order_id, symbol)",
            "description": "撤销订单",
            "endpoint": "DELETE /api/v1/order",
            "action": "orderCancel",
            "returns": "Bool - 撤销结果"
        },
        {
            "function": "get_open_orders(symbol)",
            "description": "获取当前挂单",
            "endpoint": "GET /api/v1/orders",
            "action": "orderQueryAll",
            "returns": "List[Dict] - 当前挂单列表"
        }
    ]

    # 创建接口表格
    table = Table(title="🔒 Backpack私有API接口")
    table.add_column("方法", style="cyan")
    table.add_column("功能描述", style="blue")
    table.add_column("API端点", style="yellow")
    table.add_column("签名Action", style="magenta")
    table.add_column("返回类型", style="green")

    for interface in interfaces:
        table.add_row(
            interface["function"],
            interface["description"],
            interface["endpoint"],
            interface["action"],
            interface["returns"]
        )

    console.print(table)

    # Ed25519签名说明
    rprint(f"\n[bold yellow]🔐 Ed25519签名机制说明:[/bold yellow]")
    rprint(f"[white]1. 私钥格式:[/white] Base64编码的32字节Ed25519私钥")
    rprint(f"[white]2. 签名字符串:[/white] instruction={{action}}{{params}}&timestamp={{timestamp}}&window={{window}}")
    rprint(f"[white]3. HTTP头部:[/white]")
    rprint(f"   - X-API-Key: Base64编码的公钥")
    rprint(f"   - X-Signature: Base64编码的签名")
    rprint(f"   - X-Timestamp: 毫秒时间戳")
    rprint(f"   - X-Window: 请求有效时间窗口")

    # 示例订单参数
    rprint(f"\n[bold yellow]📋 永续合约下单参数示例:[/bold yellow]")
    order_example = {
        "symbol": "BTC_USDC_PERP",
        "side": "Bid",  # Bid=买入, Ask=卖出
        "orderType": "Limit",  # Limit=限价, Market=市价
        "quantity": "0.001",
        "price": "100000.0",
        "timeInForce": "GTC"  # GTC, IOC, FOK
    }

    table = Table(title="📝 下单参数格式")
    table.add_column("参数", style="cyan")
    table.add_column("值", style="yellow")
    table.add_column("说明", style="white")

    for key, value in order_example.items():
        description = {
            "symbol": "交易对（永续合约格式）",
            "side": "方向（Bid=买入, Ask=卖出）",
            "orderType": "订单类型（Limit=限价, Market=市价）",
            "quantity": "数量（字符串格式）",
            "price": "价格（字符串格式，限价单必填）",
            "timeInForce": "有效期（GTC=撤销前有效, IOC=立即成交或撤销）"
        }.get(key, "")

        table.add_row(key, str(value), description)

    console.print(table)

    rprint(f"\n[green]✅ 私有API接口演示完成[/green]")


async def main():
    """主演示函数"""
    rprint("[bold green]🚀 Backpack交易所API功能完整演示[/bold green]")
    rprint("[dim]演示Backpack交易所的公开API和私有API接口结构[/dim]\n")

    # 演示公开API
    await demo_public_apis()

    rprint("\n" + "="*80 + "\n")

    # 演示私有API接口
    await demo_private_api_interfaces()

    rprint(f"\n[bold green]🎉 Backpack API演示完成！[/bold green]")
    rprint("[dim]所有API接口已经实现并可以正常工作，只需提供有效的Ed25519密钥对即可使用私有功能。[/dim]")


if __name__ == "__main__":
    asyncio.run(main())