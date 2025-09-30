"""
数据统计命令
"""

import click
import asyncio
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from datetime import datetime, timedelta
from typing import Optional

console = Console()


@click.group()
def stats_group():
    """📊 数据统计"""
    pass


@stats_group.command()
@click.option('--days', default=7, type=int, help='统计天数 (默认: 7天)')
@click.pass_context
def overview(ctx, days: int):
    """交易概览"""
    async def _overview():
        try:
            rprint(f"[blue]📊 获取近 {days} 天交易概览...[/blue]")

            # 模拟统计数据
            stats = {
                "total_sessions": 15,
                "active_sessions": 3,
                "completed_sessions": 10,
                "failed_sessions": 2,
                "total_volume": 850000.0,
                "total_fees": 425.50,
                "total_pnl": 2156.78,
                "aster_volume": 450000.0,
                "okx_volume": 400000.0,
                "aster_fees": 225.25,
                "okx_fees": 200.25,
                "win_rate": 85.5,
                "avg_profit_per_session": 143.78
            }

            # 创建概览表格
            table = Table(title=f"📊 交易概览 (近 {days} 天)")
            table.add_column("指标", style="cyan")
            table.add_column("数值", justify="right", style="white")
            table.add_column("详情", style="dim")

            # 会话统计
            table.add_row("总会话数", str(stats['total_sessions']), f"活跃: {stats['active_sessions']}, 完成: {stats['completed_sessions']}, 失败: {stats['failed_sessions']}")

            # 交易量统计
            table.add_row("总交易量", f"${stats['total_volume']:,.0f}", f"Aster: ${stats['aster_volume']:,.0f}, OKX: ${stats['okx_volume']:,.0f}")

            # 盈亏统计
            pnl_color = "green" if stats['total_pnl'] >= 0 else "red"
            table.add_row("总盈亏", f"[{pnl_color}]{'+' if stats['total_pnl'] >= 0 else ''}${stats['total_pnl']:,.2f}[/{pnl_color}]", f"平均每会话: ${stats['avg_profit_per_session']:.2f}")

            # 手续费统计
            table.add_row("总手续费", f"${stats['total_fees']:.2f}", f"Aster: ${stats['aster_fees']:.2f}, OKX: ${stats['okx_fees']:.2f}")

            # 胜率
            table.add_row("胜率", f"{stats['win_rate']:.1f}%", "盈利会话比例")

            console.print(table)

            # 显示图表（简单的条形图）
            rprint("\n[bold blue]📈 盈亏分布 (近7天)[/bold blue]")
            daily_pnl = [180.5, -45.2, 320.8, 156.4, -23.1, 290.6, 187.3]
            days_labels = [(datetime.now() - timedelta(days=6-i)).strftime("%m-%d") for i in range(7)]

            for i, (day, pnl) in enumerate(zip(days_labels, daily_pnl)):
                bar_length = int(abs(pnl) / 10)
                color = "green" if pnl >= 0 else "red"
                bar = "█" * min(bar_length, 20)
                rprint(f"{day}: [{color}]{'+'if pnl>=0 else ''}{pnl:6.1f} {bar}[/{color}]")

        except Exception as e:
            rprint(f"[red]❌ 获取统计数据失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_overview())


@stats_group.command()
@click.option('--period', default='daily', type=click.Choice(['daily', 'weekly', 'monthly']), help='统计周期')
@click.option('--limit', default=10, type=int, help='显示条数')
@click.pass_context
def volume(ctx, period: str, limit: int):
    """交易量统计"""
    async def _volume():
        try:
            rprint(f"[blue]📊 获取{period}交易量统计 (前{limit}条)...[/blue]")

            # 模拟交易量数据
            volume_data = []
            for i in range(limit):
                date = datetime.now() - timedelta(days=i)
                volume_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "total_volume": 85000 + (i * 2000) + (i % 3 * 5000),
                    "aster_volume": 45000 + (i * 1000),
                    "okx_volume": 40000 + (i * 1000),
                    "trade_count": 15 + (i % 5)
                })

            # 创建交易量表格
            table = Table(title=f"📊 {period.title()} 交易量统计")
            table.add_column("日期", style="cyan")
            table.add_column("总交易量", justify="right", style="white")
            table.add_column("Aster 交易量", justify="right", style="green")
            table.add_column("OKX 交易量", justify="right", style="blue")
            table.add_column("交易次数", justify="right", style="yellow")

            for data in volume_data:
                table.add_row(
                    data['date'],
                    f"${data['total_volume']:,.0f}",
                    f"${data['aster_volume']:,.0f}",
                    f"${data['okx_volume']:,.0f}",
                    str(data['trade_count'])
                )

            console.print(table)

        except Exception as e:
            rprint(f"[red]❌ 获取交易量统计失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_volume())


@stats_group.command()
@click.option('--period', default='daily', type=click.Choice(['daily', 'weekly', 'monthly']), help='统计周期')
@click.option('--limit', default=10, type=int, help='显示条数')
@click.pass_context
def pnl(ctx, period: str, limit: int):
    """盈亏统计"""
    async def _pnl():
        try:
            rprint(f"[blue]📊 获取{period}盈亏统计 (前{limit}条)...[/blue]")

            # 模拟盈亏数据
            pnl_data = []
            for i in range(limit):
                date = datetime.now() - timedelta(days=i)
                total_pnl = 150 + (i * 20) - (i % 4 * 50)
                realized_pnl = total_pnl * 0.8
                unrealized_pnl = total_pnl * 0.2

                pnl_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "total_pnl": total_pnl,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": unrealized_pnl,
                    "win_rate": 85.5 + (i % 3 * 5),
                    "avg_profit_per_trade": total_pnl / (15 + i % 5)
                })

            # 创建盈亏表格
            table = Table(title=f"📊 {period.title()} 盈亏统计")
            table.add_column("日期", style="cyan")
            table.add_column("总盈亏", justify="right")
            table.add_column("已实现盈亏", justify="right", style="green")
            table.add_column("未实现盈亏", justify="right", style="yellow")
            table.add_column("胜率", justify="right", style="blue")
            table.add_column("平均每笔利润", justify="right", style="white")

            for data in pnl_data:
                # 盈亏颜色
                total_color = "green" if data['total_pnl'] >= 0 else "red"
                realized_color = "green" if data['realized_pnl'] >= 0 else "red"
                unrealized_color = "green" if data['unrealized_pnl'] >= 0 else "red"

                table.add_row(
                    data['date'],
                    f"[{total_color}]{'+' if data['total_pnl'] >= 0 else ''}${data['total_pnl']:.2f}[/{total_color}]",
                    f"[{realized_color}]{'+' if data['realized_pnl'] >= 0 else ''}${data['realized_pnl']:.2f}[/{realized_color}]",
                    f"[{unrealized_color}]{'+' if data['unrealized_pnl'] >= 0 else ''}${data['unrealized_pnl']:.2f}[/{unrealized_color}]",
                    f"{data['win_rate']:.1f}%",
                    f"${data['avg_profit_per_trade']:.2f}"
                )

            console.print(table)

        except Exception as e:
            rprint(f"[red]❌ 获取盈亏统计失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_pnl())


@stats_group.command()
@click.option('--period', default='daily', type=click.Choice(['daily', 'weekly', 'monthly']), help='统计周期')
@click.option('--limit', default=10, type=int, help='显示条数')
@click.pass_context
def fees(ctx, period: str, limit: int):
    """手续费统计"""
    async def _fees():
        try:
            rprint(f"[blue]📊 获取{period}手续费统计 (前{limit}条)...[/blue]")

            # 模拟手续费数据
            fee_data = []
            for i in range(limit):
                date = datetime.now() - timedelta(days=i)
                total_fees = 25.50 + (i * 2.5)
                aster_fees = total_fees * 0.55
                okx_fees = total_fees * 0.45

                fee_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "total_fees": total_fees,
                    "aster_fees": aster_fees,
                    "okx_fees": okx_fees,
                    "funding_fees": total_fees * 0.1
                })

            # 创建手续费表格
            table = Table(title=f"📊 {period.title()} 手续费统计")
            table.add_column("日期", style="cyan")
            table.add_column("总手续费", justify="right", style="red")
            table.add_column("Aster 手续费", justify="right", style="green")
            table.add_column("OKX 手续费", justify="right", style="blue")
            table.add_column("资金费率", justify="right", style="yellow")

            total_all_fees = 0
            for data in fee_data:
                total_all_fees += data['total_fees']
                table.add_row(
                    data['date'],
                    f"${data['total_fees']:.2f}",
                    f"${data['aster_fees']:.2f}",
                    f"${data['okx_fees']:.2f}",
                    f"${data['funding_fees']:.2f}"
                )

            console.print(table)
            rprint(f"\n[bold red]总手续费: ${total_all_fees:.2f}[/bold red]")

        except Exception as e:
            rprint(f"[red]❌ 获取手续费统计失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_fees())


@stats_group.command()
@click.option('--limit', default=10, type=int, help='显示条数')
@click.pass_context
def accounts(ctx, limit: int):
    """账户绩效统计"""
    async def _accounts():
        try:
            rprint(f"[blue]📊 获取账户绩效统计 (前{limit}个账户)...[/blue]")

            # 模拟账户绩效数据
            account_data = [
                {
                    "account_name": "Aster 主账户",
                    "exchange": "Aster",
                    "total_volume": 450000.0,
                    "total_trades": 125,
                    "total_fees": 225.50,
                    "total_pnl": 1256.78,
                    "win_rate": 87.2,
                    "avg_profit_per_trade": 10.05
                },
                {
                    "account_name": "OKX 专业版",
                    "exchange": "OKX",
                    "total_volume": 380000.0,
                    "total_trades": 98,
                    "total_fees": 190.25,
                    "total_pnl": 845.32,
                    "win_rate": 82.7,
                    "avg_profit_per_trade": 8.63
                },
                {
                    "account_name": "Aster 备用账户",
                    "exchange": "Aster",
                    "total_volume": 120000.0,
                    "total_trades": 45,
                    "total_fees": 60.15,
                    "total_pnl": 278.45,
                    "win_rate": 84.4,
                    "avg_profit_per_trade": 6.19
                }
            ]

            # 创建账户绩效表格
            table = Table(title="📊 账户绩效统计")
            table.add_column("账户名称", style="cyan")
            table.add_column("交易所", style="blue")
            table.add_column("总交易量", justify="right", style="white")
            table.add_column("交易次数", justify="right", style="yellow")
            table.add_column("总盈亏", justify="right")
            table.add_column("胜率", justify="right", style="green")
            table.add_column("平均利润", justify="right", style="white")

            total_volume = 0
            total_pnl = 0
            for data in account_data[:limit]:
                total_volume += data['total_volume']
                total_pnl += data['total_pnl']

                pnl_color = "green" if data['total_pnl'] >= 0 else "red"

                table.add_row(
                    data['account_name'],
                    data['exchange'],
                    f"${data['total_volume']:,.0f}",
                    str(data['total_trades']),
                    f"[{pnl_color}]{'+' if data['total_pnl'] >= 0 else ''}${data['total_pnl']:.2f}[/{pnl_color}]",
                    f"{data['win_rate']:.1f}%",
                    f"${data['avg_profit_per_trade']:.2f}"
                )

            console.print(table)

            # 显示汇总
            rprint(f"\n[bold]总交易量: ${total_volume:,.0f}[/bold]")
            total_pnl_color = "green" if total_pnl >= 0 else "red"
            rprint(f"[bold]总盈亏: [{total_pnl_color}]{'+' if total_pnl >= 0 else ''}${total_pnl:.2f}[/{total_pnl_color}][/bold]")

        except Exception as e:
            rprint(f"[red]❌ 获取账户绩效失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_accounts())