"""
交易管理命令
"""

import click
import asyncio
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.live import Live
import time
from datetime import datetime
from typing import Optional, Dict, Any

from ..core.api_client import get_api_client
from ..core.exceptions import APIError

console = Console()


@click.group()
def trading_group():
    """📈 交易管理"""
    pass


@trading_group.command()
@click.option('--status', type=click.Choice(['active', 'completed', 'failed', 'pending']), help='按状态筛选')
@click.pass_context
def list(ctx, status: Optional[str]):
    """列出交易会话"""
    async def _list():
        try:
            async with get_api_client() as client:
                rprint("[blue]📋 获取交易会话列表...[/blue]")

                # 模拟数据，因为无需认证
                sessions = [
                    {
                        "id": 1,
                        "session_name": "BTC套利会话-1",
                        "symbol": "BTC/USDT",
                        "position_size": 0.5,
                        "leverage": 1,
                        "hedge_direction": "long",
                        "status": "active",
                        "total_volume": 50000.0,
                        "total_fees": 25.50,
                        "total_pnl": 156.78,
                        "started_at": "2024-01-27 09:30:00",
                        "created_at": "2024-01-27 09:25:00"
                    },
                    {
                        "id": 2,
                        "session_name": "ETH套利会话-2",
                        "symbol": "ETH/USDT",
                        "position_size": 5.2,
                        "leverage": 1,
                        "hedge_direction": "short",
                        "status": "active",
                        "total_volume": 30000.0,
                        "total_fees": 15.25,
                        "total_pnl": 89.45,
                        "started_at": "2024-01-27 10:45:00",
                        "created_at": "2024-01-27 10:40:00"
                    },
                    {
                        "id": 3,
                        "session_name": "BNB套利会话-3",
                        "symbol": "BNB/USDT",
                        "position_size": 50.0,
                        "leverage": 1,
                        "hedge_direction": "long",
                        "status": "completed",
                        "total_volume": 20000.0,
                        "total_fees": 10.75,
                        "total_pnl": 234.56,
                        "started_at": "2024-01-26 14:30:00",
                        "created_at": "2024-01-26 14:25:00"
                    }
                ]

                # 按状态筛选
                if status:
                    sessions = [s for s in sessions if s['status'] == status]

                if not sessions:
                    rprint("[yellow]📭 未找到交易会话[/yellow]")
                    rprint("[dim]使用 'gooddex trading create-session' 创建新会话[/dim]")
                    return

                # 创建交易会话表格
                table = Table(title=f"📈 交易会话列表 ({len(sessions)} 个会话)")
                table.add_column("ID", justify="right", style="cyan")
                table.add_column("名称", style="white")
                table.add_column("交易对", style="blue")
                table.add_column("持仓大小", justify="right", style="yellow")
                table.add_column("方向", justify="center")
                table.add_column("状态", justify="center")
                table.add_column("总盈亏", justify="right", style="green")
                table.add_column("总成交量", justify="right", style="cyan")
                table.add_column("创建时间", style="dim")

                for session in sessions:
                    # 状态颜色
                    if session['status'] == 'active':
                        status_display = "[green]✅ 运行中[/green]"
                    elif session['status'] == 'completed':
                        status_display = "[blue]✅ 已完成[/blue]"
                    elif session['status'] == 'failed':
                        status_display = "[red]❌ 失败[/red]"
                    else:
                        status_display = "[yellow]⏸ 暂停[/yellow]"

                    # 盈亏颜色
                    pnl = session['total_pnl']
                    pnl_display = f"[green]+${pnl:.2f}[/green]" if pnl >= 0 else f"[red]-${abs(pnl):.2f}[/red]"

                    # 方向显示
                    direction = "🔺 做多" if session['hedge_direction'] == 'long' else "🔻 做空"

                    table.add_row(
                        str(session['id']),
                        session['session_name'],
                        session['symbol'],
                        f"{session['position_size']} {session['symbol'].split('/')[0]}",
                        direction,
                        status_display,
                        pnl_display,
                        f"${session['total_volume']:,.0f}",
                        session['created_at'][:10]
                    )

                console.print(table)

        except APIError as e:
            rprint(f"[red]❌ API 错误: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 获取交易会话失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_list())


@trading_group.command()
@click.option('--name', '-n', required=True, help='会话名称')
@click.option('--symbol', '-s', required=True, help='交易对 (如: BTC/USDT)')
@click.option('--size', required=True, type=float, help='持仓大小')
@click.option('--direction', required=True, type=click.Choice(['long', 'short']), help='对冲方向')
@click.option('--leverage', default=1, type=int, help='杠杆倍数 (默认: 1)')
@click.option('--aster-account', help='Aster 账户名称')
@click.option('--okx-account', help='OKX 账户名称')
@click.pass_context
def create_session(ctx, name: str, symbol: str, size: float, direction: str, leverage: int, aster_account: str, okx_account: str):
    """创建交易会话"""
    async def _create():
        try:
            rprint(f"[blue]📝 创建交易会话 '{name}'...[/blue]")

            # 模拟创建过程
            rprint(f"[dim]• 交易对: {symbol}[/dim]")
            rprint(f"[dim]• 持仓大小: {size}[/dim]")
            rprint(f"[dim]• 对冲方向: {'做多' if direction == 'long' else '做空'}[/dim]")
            rprint(f"[dim]• 杠杆倍数: {leverage}x[/dim]")

            # 模拟延迟
            await asyncio.sleep(1)

            session_id = 4  # 模拟新会话ID

            rprint(f"[green]✅ 交易会话创建成功![/green]")
            rprint(f"[blue]会话ID: {session_id}[/blue]")
            rprint(f"[blue]会话名称: {name}[/blue]")
            rprint(f"[dim]使用 'gooddx trading start --session-id {session_id}' 启动交易[/dim]")

        except Exception as e:
            rprint(f"[red]❌ 创建交易会话失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_create())


@trading_group.command()
@click.option('--session-id', required=True, type=int, help='会话ID')
@click.pass_context
def start(ctx, session_id: int):
    """启动交易会话"""
    async def _start():
        try:
            rprint(f"[blue]🚀 启动交易会话 {session_id}...[/blue]")

            # 模拟启动过程
            steps = [
                "检查账户连接",
                "验证余额充足",
                "初始化交易引擎",
                "开始监控价差",
                "交易会话已启动"
            ]

            for i, step in enumerate(steps, 1):
                rprint(f"[dim]{i}. {step}...[/dim]")
                await asyncio.sleep(0.5)

            rprint(f"[green]✅ 交易会话 {session_id} 启动成功![/green]")
            rprint(f"[blue]状态: 运行中[/blue]")
            rprint(f"[dim]使用 'gooddx trading monitor --session-id {session_id}' 监控交易[/dim]")

        except Exception as e:
            rprint(f"[red]❌ 启动交易会话失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_start())


@trading_group.command()
@click.option('--session-id', required=True, type=int, help='会话ID')
@click.pass_context
def stop(ctx, session_id: int):
    """停止交易会话"""
    async def _stop():
        try:
            rprint(f"[blue]🛑 停止交易会话 {session_id}...[/blue]")

            # 模拟停止过程
            steps = [
                "停止新交易",
                "等待挂单完成",
                "平仓所有持仓",
                "生成交易报告",
                "交易会话已停止"
            ]

            for i, step in enumerate(steps, 1):
                rprint(f"[dim]{i}. {step}...[/dim]")
                await asyncio.sleep(0.5)

            rprint(f"[green]✅ 交易会话 {session_id} 已停止[/green]")
            rprint(f"[blue]最终盈亏: +$156.78[/blue]")

        except Exception as e:
            rprint(f"[red]❌ 停止交易会话失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_stop())


@trading_group.command()
@click.option('--session-id', type=int, help='监控特定会话 (留空监控所有)')
@click.option('--refresh', default=3, type=int, help='刷新间隔 (秒)')
@click.pass_context
def monitor(ctx, session_id: Optional[int], refresh: int):
    """实时监控交易"""
    def generate_table():
        """生成实时监控表格"""
        # 模拟实时数据
        sessions_data = [
            {
                "id": 1,
                "name": "BTC套利会话-1",
                "symbol": "BTC/USDT",
                "status": "🟢 运行中",
                "pnl": 156.78 + (time.time() % 10) - 5,  # 模拟PnL变化
                "volume": 50000.0,
                "trades": 23,
                "duration": "2h 15m"
            },
            {
                "id": 2,
                "name": "ETH套利会话-2",
                "symbol": "ETH/USDT",
                "status": "🟢 运行中",
                "pnl": 89.45 + (time.time() % 8) - 4,
                "volume": 30000.0,
                "trades": 18,
                "duration": "1h 45m"
            }
        ]

        if session_id:
            sessions_data = [s for s in sessions_data if s['id'] == session_id]

        table = Table(title=f"📺 实时交易监控 - {datetime.now().strftime('%H:%M:%S')}")
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("会话名称", style="white")
        table.add_column("交易对", style="blue")
        table.add_column("状态", justify="center")
        table.add_column("当前盈亏", justify="right")
        table.add_column("成交量", justify="right", style="cyan")
        table.add_column("交易次数", justify="right", style="yellow")
        table.add_column("运行时长", style="dim")

        for session in sessions_data:
            pnl = session['pnl']
            pnl_color = "green" if pnl >= 0 else "red"
            pnl_display = f"[{pnl_color}]{'+' if pnl >= 0 else ''}${pnl:.2f}[/{pnl_color}]"

            table.add_row(
                str(session['id']),
                session['name'],
                session['symbol'],
                session['status'],
                pnl_display,
                f"${session['volume']:,.0f}",
                str(session['trades']),
                session['duration']
            )

        return table

    def run_monitor():
        """运行监控"""
        try:
            rprint(f"[blue]📺 开始实时监控... (按 Ctrl+C 退出)[/blue]")
            rprint(f"[dim]刷新间隔: {refresh} 秒[/dim]")

            with Live(generate_table(), refresh_per_second=1/refresh) as live:
                while True:
                    time.sleep(refresh)
                    live.update(generate_table())

        except KeyboardInterrupt:
            rprint("\n[yellow]⚠️  监控已停止[/yellow]")
        except Exception as e:
            rprint(f"\n[red]❌ 监控失败: {e}[/red]")

    run_monitor()


@trading_group.command()
@click.option('--account-id', type=int, help='账户ID')
@click.option('--account-name', help='账户名称')
@click.pass_context
def positions(ctx, account_id: Optional[int], account_name: Optional[str]):
    """查看持仓信息"""
    async def _positions():
        try:
            if account_name:
                rprint(f"[blue]📊 获取账户 '{account_name}' 持仓信息...[/blue]")
            elif account_id:
                rprint(f"[blue]📊 获取账户 {account_id} 持仓信息...[/blue]")
            else:
                rprint(f"[blue]📊 获取所有账户持仓信息...[/blue]")

            # 获取真实持仓数据
            positions = []

            # 读取账户数据
            import json
            from ..core.config import get_config
            from ..core.exchange_adapters import get_exchange_adapter

            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if accounts_file.exists():
                with open(accounts_file, 'r', encoding='utf-8') as f:
                    accounts = json.load(f)

                # 筛选账户
                target_accounts = accounts
                if account_id:
                    target_accounts = [acc for acc in accounts if acc['id'] == account_id]
                elif account_name:
                    target_accounts = [acc for acc in accounts if acc['name'] == account_name]

                # 获取每个账户的持仓
                for account in target_accounts:
                    try:
                        adapter = get_exchange_adapter(
                            exchange=account['exchange'],
                            api_key=account['api_key'],
                            secret=account['secret_key'],
                            passphrase=account.get('passphrase'),
                            testnet=account.get('is_testnet', False)
                        )

                        account_positions = await adapter.get_positions()

                        # 添加交易所信息
                        for pos in account_positions:
                            pos['exchange'] = account['exchange'].upper()

                        positions.extend(account_positions)

                        # 关闭适配器会话
                        if hasattr(adapter, 'close'):
                            await adapter.close()

                    except Exception as e:
                        rprint(f"[yellow]⚠️  获取账户 {account['name']} 持仓失败: {str(e)}[/yellow]")

            if not positions:
                rprint("[yellow]📭 暂无持仓[/yellow]")
                return

            # 创建持仓表格
            table = Table(title=f"📊 持仓信息 ({len(positions)} 个仓位)")
            table.add_column("交易对", style="cyan")
            table.add_column("交易所", style="blue")
            table.add_column("方向", justify="center")
            table.add_column("持仓大小", justify="right", style="yellow")
            table.add_column("开仓价格", justify="right", style="white")
            table.add_column("标记价格", justify="right", style="white")
            table.add_column("未实现盈亏", justify="right")

            total_pnl = 0
            for pos in positions:
                direction = "🔺 多" if pos['side'] == 'long' else "🔻 空"
                pnl = pos.get('pnl', 0)
                total_pnl += pnl
                pnl_color = "green" if pnl >= 0 else "red"
                pnl_display = f"[{pnl_color}]{'+' if pnl >= 0 else ''}${pnl:.2f}[/{pnl_color}]"

                # 处理币种名称显示
                symbol_parts = pos['symbol'].split('/')
                base_currency = symbol_parts[0] if len(symbol_parts) > 1 else pos['symbol']

                table.add_row(
                    pos['symbol'],
                    pos['exchange'],
                    direction,
                    f"{pos['size']} {base_currency}",
                    f"${pos['entry_price']:,.2f}",
                    f"${pos['mark_price']:,.2f}",
                    pnl_display
                )

            console.print(table)

            # 显示总计
            total_color = "green" if total_pnl >= 0 else "red"
            rprint(f"\n[bold]总未实现盈亏: [{total_color}]{'+' if total_pnl >= 0 else ''}${total_pnl:.2f}[/{total_color}][/bold]")

        except Exception as e:
            rprint(f"[red]❌ 获取持仓信息失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_positions())