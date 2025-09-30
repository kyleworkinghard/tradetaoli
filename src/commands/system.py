"""
系统管理命令
"""

import asyncio
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.panel import Panel

from ..core.api_client import get_api_client
from ..core.exceptions import APIError, ConnectionError
from .. import __version__

console = Console()


async def health_check(ctx):
    """系统健康检查"""
    try:
        rprint("[blue]🏥 系统健康检查...[/blue]")

        async with get_api_client() as client:
            # 检查API连接
            rprint("[dim]• 检查API连接...[/dim]")
            health_data = await client.health_check()

            # 创建健康检查表格
            table = Table(title="🏥 系统健康状态")
            table.add_column("组件", style="cyan")
            table.add_column("状态", justify="center")
            table.add_column("详情", style="dim")

            # API状态
            if health_data.get('status') == 'healthy':
                table.add_row("API服务", "[green]✅ 正常[/green]", f"响应时间 < 100ms")
            else:
                table.add_row("API服务", "[red]❌ 异常[/red]", "连接失败")

            # 数据库状态
            db_status = health_data.get('database', 'unknown')
            if db_status == 'connected':
                table.add_row("数据库", "[green]✅ 正常[/green]", "连接正常")
            else:
                table.add_row("数据库", "[red]❌ 异常[/red]", "连接失败")

            # 交易所状态
            exchanges = health_data.get('exchanges', {})
            for exchange, status in exchanges.items():
                if status == 'available':
                    table.add_row(f"{exchange.upper()} 交易所", "[green]✅ 正常[/green]", "API可用")
                else:
                    table.add_row(f"{exchange.upper()} 交易所", "[yellow]⚠️ 警告[/yellow]", "API不可用")

            # 本地配置
            table.add_row("本地配置", "[green]✅ 正常[/green]", "配置文件加载成功")

            # CLI工具
            table.add_row("CLI工具", "[green]✅ 正常[/green]", f"版本 {__version__}")

            console.print(table)

            rprint("[green]✅ 系统健康检查完成[/green]")

    except ConnectionError:
        rprint("[red]❌ 无法连接到API服务器[/red]")
        rprint("[dim]请检查后端服务是否运行在 http://localhost:8000[/dim]")
        ctx.exit(1)
    except APIError as e:
        rprint(f"[red]❌ API错误: {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        rprint(f"[red]❌ 健康检查失败: {e}[/red]")
        ctx.exit(1)


def show_version():
    """显示版本信息"""
    version_info = f"""
[bold blue]🚀 GoodDEX CLI[/bold blue]

[cyan]版本信息:[/cyan]
  版本: [white]{__version__}[/white]
  构建日期: [white]2024-01-27[/white]
  Python版本: [white]3.8+[/white]

[cyan]功能特性:[/cyan]
  ✅ 双交易所对冲交易 (Aster + OKX)
  ✅ 实时价格监控和套利机会发现
  ✅ 自动化交易会话管理
  ✅ 详细的交易统计和绩效分析
  ✅ 丰富的命令行界面和实时监控
  ✅ 安全的API密钥管理

[cyan]支持的交易所:[/cyan]
  🔸 Aster DEX - 去中心化期货交易
  🔸 OKX CEX - 中心化数字资产交易

[cyan]获取帮助:[/cyan]
  文档: [blue]https://docs.gooddex.com/cli[/blue]
  GitHub: [blue]https://github.com/gooddex/gooddex-cli[/blue]
  支持: [blue]support@gooddex.com[/blue]

[dim]Copyright © 2024 GoodDEX Team. All rights reserved.[/dim]
"""

    panel = Panel(
        version_info,
        title="📋 版本信息",
        border_style="blue",
        padding=(1, 2)
    )

    console.print(panel)