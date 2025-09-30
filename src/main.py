#!/usr/bin/env python3
"""
GoodDEX CLI - 主入口模块
专业的双交易所对冲交易终端工具
"""

import click
import sys
import asyncio
from rich.console import Console
from rich.traceback import install
from rich import print as rprint

# 安装 rich 异常处理
install(show_locals=True)

# 全局控制台对象
console = Console()

from .commands.auth import auth_group
from .commands.account import account_group
from .commands.trading import trading_group
from .commands.stats import stats_group
from .commands.config import config_group
from .commands.monitor import monitor_group
from .commands.arbitrage import arbitrage_group
from .core.config import get_config
from .core.exceptions import GoodDEXError
from . import __version__


@click.group(invoke_without_command=True)
@click.option('--version', is_flag=True, help='显示版本信息')
@click.option('--config-file', type=click.Path(), help='指定配置文件路径')
@click.option('--debug', is_flag=True, help='启用调试模式')
@click.pass_context
def cli(ctx, version, config_file, debug):
    """
    🚀 GoodDEX CLI - 专业的双交易所对冲交易终端

    支持 Aster DEX 和 OKX CEX 的自动化对冲交易工具
    """
    # 确保上下文对象存在
    ctx.ensure_object(dict)

    # 存储全局配置
    ctx.obj['config_file'] = config_file
    ctx.obj['debug'] = debug

    if version:
        rprint(f"[bold blue]GoodDEX CLI[/bold blue] v{__version__}")
        rprint(f"[dim]专业的双交易所对冲交易终端工具[/dim]")
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        # 显示欢迎信息和帮助
        show_welcome()
        click.echo(ctx.get_help())


def show_welcome():
    """显示欢迎信息"""
    rprint("""
[bold blue]
    ╔═══════════════════════════════════════╗
    ║           GoodDEX CLI v{version}           ║
    ║     专业双交易所对冲交易终端            ║
    ╚═══════════════════════════════════════╝
[/bold blue]

[yellow]🚀 快速开始:[/yellow]
  [dim]1.[/dim] [cyan]gooddex auth login[/cyan]                 # 登录系统
  [dim]2.[/dim] [cyan]gooddex account add[/cyan]                # 添加交易账户
  [dim]3.[/dim] [cyan]gooddex trading create-session[/cyan]     # 创建交易会话
  [dim]4.[/dim] [cyan]gooddex trading start[/cyan]              # 启动交易
  [dim]5.[/dim] [cyan]gooddx monitor[/cyan]                     # 实时监控

[yellow]📚 帮助:[/yellow]
  [cyan]gooddex --help[/cyan]                      # 显示帮助
  [cyan]gooddex <command> --help[/cyan]            # 显示命令帮助
""".format(version=__version__))


@cli.group()
@click.pass_context
def auth(ctx):
    """🔐 认证管理"""
    pass


@cli.group()
@click.pass_context
def account(ctx):
    """💰 账户管理"""
    pass


@cli.group()
@click.pass_context
def trading(ctx):
    """📈 交易管理"""
    pass


@cli.group()
@click.pass_context
def stats(ctx):
    """📊 数据统计"""
    pass


@cli.group()
@click.pass_context
def config(ctx):
    """⚙️  配置管理"""
    pass


@cli.group()
@click.pass_context
def monitor(ctx):
    """📺 实时监控"""
    pass


@cli.group()
@click.pass_context
def arbitrage(ctx):
    """🔄 自动化套利交易"""
    pass


@cli.command()
@click.pass_context
def health(ctx):
    """🏥 系统健康检查"""
    from .commands.system import health_check
    asyncio.run(health_check(ctx))


@cli.command()
def version():
    """📋 显示版本信息"""
    from .commands.system import show_version
    show_version()


# 注册命令组
cli.add_command(auth_group, name='auth')
cli.add_command(account_group, name='account')
cli.add_command(trading_group, name='trading')
cli.add_command(stats_group, name='stats')
cli.add_command(config_group, name='config')
cli.add_command(monitor_group, name='monitor')
cli.add_command(arbitrage_group, name='arbitrage')


def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理"""
    if issubclass(exc_type, GoodDEXError):
        console.print(f"[red]❌ 错误: {exc_value}[/red]")
    elif issubclass(exc_type, KeyboardInterrupt):
        console.print("\n[yellow]⚠️  操作已取消[/yellow]")
    else:
        console.print_exception()
    sys.exit(1)


# 设置全局异常处理
sys.excepthook = handle_exception


if __name__ == '__main__':
    cli()