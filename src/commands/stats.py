"""
真实交易统计分析模块
"""

import click
import asyncio
from datetime import datetime, timedelta
from rich.table import Table
from rich.console import Console
from rich import print as rprint
from typing import Dict, List, Any

from ..core.exchange_factory import ExchangeFactory

console = Console()

@click.group()
def stats_group():
    """📊 真实交易统计分析"""
    pass


@stats_group.command()
@click.option('--account-id', type=int, help='特定账户ID')
@click.option('--days', default=7, type=int, help='统计天数 (默认7天)')  
@click.option('--symbol', help='特定交易对')
def overview(account_id, days, symbol):
    """查看真实交易统计概览"""
    asyncio.run(_overview(account_id, days, symbol))


async def _overview(account_id: int = None, days: int = 7, symbol: str = None):
    """统计概览实现 - 访问真实数据"""
    try:
        factory = ExchangeFactory()
        accounts = factory.load_accounts()

        rprint(f"[blue]📊 开始分析真实交易数据 (近{days}天)[/blue]")

        # 确定要统计的账户
        target_accounts = [account_id] if account_id else list(accounts.keys())

        if not target_accounts:
            rprint("[red]❌ 没有找到任何账户配置[/red]")
            return

        total_stats = {
            'total_volume': 0.0,
            'total_fees': 0.0,
            'total_trades': 0,
            'accounts_data': []
        }

        # 分析每个账户
        for acc_id in target_accounts:
            if acc_id not in accounts:
                rprint(f"[yellow]⚠️ 跳过不存在的账户 {acc_id}[/yellow]")
                continue

            rprint(f"[cyan]🔍 正在分析账户 {acc_id} ({accounts[acc_id]['exchange']})...[/cyan]")

            # 获取账户统计
            account_stats = await _analyze_account_history(factory, acc_id, days, symbol)
            total_stats['accounts_data'].append(account_stats)

            # 累计总统计
            total_stats['total_volume'] += account_stats['volume']
            total_stats['total_fees'] += account_stats['fees']
            total_stats['total_trades'] += account_stats['trades']

        # 显示真实结果
        _display_summary_table(total_stats)

        # 如果没有任何数据，显示提示
        if total_stats['total_trades'] == 0:
            rprint(f"\n[yellow]💡 提示:[/yellow]")
            rprint(f"  - 近{days}天内没有交易记录")
            rprint(f"  - 请检查账户配置是否正确")
            rprint(f"  - 可以尝试增加天数: --days 30")

    except Exception as e:
        rprint(f"[red]❌ 统计分析失败: {e}[/red]")
        import traceback
        rprint(f"[dim]详细错误信息: {traceback.format_exc()}[/dim]")

async def _analyze_account_history(factory: ExchangeFactory, account_id: int, 
                                  days: int, symbol_filter: str = None):
    """分析单个账户的历史成交 - 真实数据版本"""
    try:
        # 创建交易所适配器
        accounts = factory.load_accounts()
        account = accounts[account_id]

        rprint(f"  📡 连接到 {account['exchange']} 交易所...")

        # 创建临时的exchange_info来获取adapter
        exchange_info = factory.create_exchange_info(account_id, symbol_filter or "BTCUSDT")
        adapter = exchange_info.adapter

        # 检查是否支持统计专用的成交历史查询
        if hasattr(adapter, 'get_trade_history_for_stats'):
            # 使用统计专用方法，不影响交易功能
            rprint(f"  🔍 正在获取 {account['exchange']} 统计数据...")
            fills = await adapter.get_trade_history_for_stats(
                symbol=symbol_filter,
                limit=1000
            )
        elif hasattr(adapter, 'get_fills_history'):
            # 使用现有方法（OKX）
            rprint(f"  🔍 正在获取 {account['exchange']} 成交历史...")
            fills = await adapter.get_fills_history(
                symbol=symbol_filter,
                limit=1000  # 获取更多记录
            )
        else:
            return {
                'account_id': account_id,
                'exchange': account['exchange'],
                'volume': 0.0,
                'fees': 0.0,
                'trades': 0,
                'pnl': 0.0,
                'error': f'{account["exchange"]} 不支持历史成交查询'
            }

        rprint(f"  📋 从 {account['exchange']} 获取到 {len(fills)} 条成交记录")

        # 如果获取到数据，显示一些样本
        if fills and len(fills) > 0:
            rprint(f"  📊 最新成交样本:")
            for i, fill in enumerate(fills[:3]):  # 显示前3条
                symbol = fill.get('symbol', 'N/A')
                side = fill.get('side', 'N/A')
                price = fill.get('price', 0)
                quantity = fill.get('quantity', 0)
                rprint(f"    {i+1}. {symbol} {side} {quantity} @ ${price}")

        # 统计分析
        stats = _calculate_trading_stats(fills, days)
        stats.update({
            'account_id': account_id,
            'exchange': account['exchange']
        })

        # 显示此账户的统计结果
        if stats['trades'] > 0:
            rprint(f"  ✅ {account['exchange']} 统计完成: {stats['trades']}笔交易, 交易量${stats['volume']:,.2f}")
        else:
            rprint(f"  ⚠️ {account['exchange']} 近{days}天无交易记录")

        return stats

    except Exception as e:
        error_msg = str(e)
        rprint(f"  [red]❌ 账户{account_id}分析失败: {error_msg}[/red]")

        return {
            'account_id': account_id,
            'exchange': accounts.get(account_id, {}).get('exchange', 'Unknown'),
            'volume': 0.0,
            'fees': 0.0,
            'trades': 0,
            'pnl': 0.0,
            'error': error_msg
        }

def _calculate_trading_stats(fills: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    """计算交易统计数据 - 增强调试版本"""
    if not fills:
        return {'volume': 0.0, 'fees': 0.0, 'trades': 0, 'pnl': 0.0, 'symbols': {}}

    rprint(f"    🔢 开始计算统计数据，原始记录数: {len(fills)}")

    # 时间过滤 - 只统计指定天数内的数据
    cutoff_time = datetime.now() - timedelta(days=days)
    rprint(f"    📅 时间过滤: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 之后的数据")

    total_volume = 0.0
    total_fees = 0.0
    total_trades = 0
    symbols_data = {}
    filtered_out = 0
    processed = 0

    for fill in fills:
        try:
            processed += 1

            # 时间过滤 (如果有时间戳)
            if 'timestamp' in fill and fill['timestamp']:
                # 处理时间戳 (毫秒转秒)
                timestamp = fill['timestamp']
                if timestamp > 1e12:  # 毫秒时间戳
                    timestamp = timestamp / 1000
                fill_time = datetime.fromtimestamp(timestamp)
                if fill_time < cutoff_time:
                    filtered_out += 1
                    continue

            symbol = fill.get('symbol', 'Unknown')
            side = fill.get('side', 'Unknown')
            price = float(fill.get('price', 0))
            quantity = float(fill.get('quantity', 0))
            fee = float(fill.get('fee', 0))

            if price <= 0 or quantity <= 0:
                continue

            # 计算交易量 (以USDT计价)
            volume = price * quantity
            total_volume += volume
            total_fees += fee
            total_trades += 1

            # 按交易对分组统计
            if symbol not in symbols_data:
                symbols_data[symbol] = {
                    'volume': 0.0,
                    'fees': 0.0,
                    'trades': 0,
                    'buy_volume': 0.0,
                    'sell_volume': 0.0
                }

            symbols_data[symbol]['volume'] += volume
            symbols_data[symbol]['fees'] += fee
            symbols_data[symbol]['trades'] += 1

            if side.lower() in ['buy', 'bid']:
                symbols_data[symbol]['buy_volume'] += volume
            else:
                symbols_data[symbol]['sell_volume'] += volume

        except (ValueError, TypeError, KeyError) as e:
            rprint(f"    [yellow]⚠️ 跳过无效记录: {e}[/yellow]")
            continue

    rprint(f"    📊 统计完成: 处理{processed}条, 过滤{filtered_out}条, 有效{total_trades}条")

    return {
        'volume': total_volume,
        'fees': total_fees,
        'trades': total_trades,
        'pnl': 0.0,  # 暂时设为0，后续可以增强
        'symbols': symbols_data
    }

def _display_summary_table(total_stats: Dict[str, Any]):
    """显示统计汇总表格"""
    # 账户汇总表
    accounts_table = Table(title="🏦 账户交易统计汇总", show_header=True, header_style="bold magenta")
    accounts_table.add_column("账户ID", style="cyan", width=8)
    accounts_table.add_column("交易所", style="green", width=12)
    accounts_table.add_column("交易量(USDT)", style="yellow", width=15, justify="right")
    accounts_table.add_column("手续费(USDT)", style="red", width=15, justify="right")
    accounts_table.add_column("交易笔数", style="blue", width=10, justify="right")
    accounts_table.add_column("状态", style="white", width=20)

    for account_data in total_stats['accounts_data']:
        if 'error' in account_data:
            status = f"❌ {account_data['error']}"
            volume_str = "-"
            fees_str = "-"
            trades_str = "-"
        else:
            status = "✅ 正常"
            volume_str = f"{account_data['volume']:,.2f}"
            fees_str = f"{account_data['fees']:,.4f}"
            trades_str = f"{account_data['trades']:,}"

        accounts_table.add_row(
            str(account_data['account_id']),
            account_data['exchange'],
            volume_str,
            fees_str,
            trades_str,
            status
        )

    console.print(accounts_table)

    # 总计信息
    rprint(f"\n[bold green]📊 统计总计:[/bold green]")
    rprint(f"  💰 总交易量: [yellow]{total_stats['total_volume']:,.2f}[/yellow] USDT")
    rprint(f"  💸 总手续费: [red]{total_stats['total_fees']:,.4f}[/red] USDT")
    rprint(f"  📈 总交易数: [blue]{total_stats['total_trades']:,}[/blue] 笔")

    if total_stats['total_volume'] > 0:
        fee_rate = (total_stats['total_fees'] / total_stats['total_volume']) * 100
        rprint(f"  📊 平均费率: [magenta]{fee_rate:.4f}%[/magenta]")

    # 显示交易对详情
    _display_symbols_detail(total_stats['accounts_data'])

def _display_symbols_detail(accounts_data: List[Dict[str, Any]]):
    """显示交易对详细统计"""
    # 合并所有账户的交易对数据
    all_symbols = {}

    for account_data in accounts_data:
        if 'error' in account_data or 'symbols' not in account_data:
            continue

        for symbol, symbol_data in account_data['symbols'].items():
            if symbol not in all_symbols:
                all_symbols[symbol] = {
                    'volume': 0.0,
                    'fees': 0.0,
                    'trades': 0,
                    'buy_volume': 0.0,
                    'sell_volume': 0.0
                }

            all_symbols[symbol]['volume'] += symbol_data['volume']
            all_symbols[symbol]['fees'] += symbol_data['fees']
            all_symbols[symbol]['trades'] += symbol_data['trades']
            all_symbols[symbol]['buy_volume'] += symbol_data.get('buy_volume', 0)
            all_symbols[symbol]['sell_volume'] += symbol_data.get('sell_volume', 0)

    if all_symbols:
        rprint(f"\n[bold blue]📈 交易对统计详情:[/bold blue]")

        symbols_table = Table(title="💱 交易对详细统计", show_header=True, header_style="bold blue")
        symbols_table.add_column("交易对", style="cyan", width=15)
        symbols_table.add_column("总交易量", style="yellow", width=15, justify="right")
        symbols_table.add_column("买入量", style="green", width=12, justify="right")
        symbols_table.add_column("卖出量", style="red", width=12, justify="right")
        symbols_table.add_column("手续费", style="magenta", width=12, justify="right")
        symbols_table.add_column("交易数", style="blue", width=8, justify="right")

        # 按交易量排序
        sorted_symbols = sorted(all_symbols.items(), key=lambda x: x[1]['volume'], reverse=True)

        for symbol, data in sorted_symbols:
            symbols_table.add_row(
                symbol,
                f"{data['volume']:,.2f}",
                f"{data['buy_volume']:,.2f}",
                f"{data['sell_volume']:,.2f}",
                f"{data['fees']:,.4f}",
                f"{data['trades']:,}"
            )

        console.print(symbols_table)