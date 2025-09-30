"""
配置管理命令
"""

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from ..core.config import get_config

console = Console()


@click.group()
def config_group():
    """⚙️ 配置管理"""
    pass


@config_group.command()
@click.pass_context
def show(ctx):
    """显示当前配置"""
    try:
        config_manager = get_config()
        config = config_manager.config

        rprint("[blue]⚙️ 当前配置[/blue]")

        # API 配置
        api_table = Table(title="🌐 API 配置", show_header=False)
        api_table.add_column("项目", style="cyan")
        api_table.add_column("值", style="white")

        api_table.add_row("基础URL", config.api.base_url)
        api_table.add_row("超时时间", f"{config.api.timeout} 秒")
        api_table.add_row("重试次数", str(config.api.retry_count))
        api_table.add_row("SSL验证", "启用" if config.api.verify_ssl else "禁用")

        console.print(api_table)

        # 交易配置
        trading_table = Table(title="📈 交易配置", show_header=False)
        trading_table.add_column("项目", style="cyan")
        trading_table.add_column("值", style="white")

        trading_table.add_row("默认杠杆", f"{config.trading.default_leverage}x")
        trading_table.add_row("最大持仓", f"{config.trading.max_position_size}")
        trading_table.add_row("风险限制", f"{config.trading.risk_limit * 100}%")
        trading_table.add_row("最小利润阈值", f"${config.trading.min_profit_threshold}")
        trading_table.add_row("最大价差阈值", f"{config.trading.max_spread_threshold}%")

        console.print(trading_table)

        # 显示配置
        display_table = Table(title="🎨 显示配置", show_header=False)
        display_table.add_column("项目", style="cyan")
        display_table.add_column("值", style="white")

        display_table.add_row("小数位数", str(config.display.decimal_places))
        display_table.add_row("时区", config.display.timezone)
        display_table.add_row("主题", config.display.color_theme)
        display_table.add_row("表格样式", config.display.table_style)

        console.print(display_table)

        rprint(f"[dim]配置文件: {config_manager.config_file}[/dim]")

    except Exception as e:
        rprint(f"[red]❌ 显示配置失败: {e}[/red]")
        ctx.exit(1)


@config_group.command()
@click.argument('key')
@click.argument('value')
@click.pass_context
def set(ctx, key: str, value: str):
    """设置配置项"""
    try:
        config_manager = get_config()

        rprint(f"[blue]⚙️ 设置配置项 {key} = {value}[/blue]")

        config_manager.set(key, value)

        rprint(f"[green]✅ 配置项已更新[/green]")
        rprint(f"[dim]配置已保存到: {config_manager.config_file}[/dim]")

    except ValueError as e:
        rprint(f"[red]❌ 配置错误: {e}[/red]")
        rprint(f"[dim]示例: gooddex config set api.timeout 60[/dim]")
        ctx.exit(1)
    except Exception as e:
        rprint(f"[red]❌ 设置配置失败: {e}[/red]")
        ctx.exit(1)


@config_group.command()
@click.argument('key')
@click.pass_context
def get(ctx, key: str):
    """获取配置项"""
    try:
        config_manager = get_config()

        value = config_manager.get(key)

        if value is None:
            rprint(f"[red]❌ 配置项 '{key}' 不存在[/red]")
            ctx.exit(1)

        rprint(f"[cyan]{key}[/cyan]: [white]{value}[/white]")

    except Exception as e:
        rprint(f"[red]❌ 获取配置失败: {e}[/red]")
        ctx.exit(1)


@config_group.command()
@click.confirmation_option(prompt='确定要重置为默认配置吗？')
@click.pass_context
def init(ctx):
    """初始化配置文件"""
    try:
        from ..core.config import init_config

        rprint("[blue]⚙️ 初始化配置文件...[/blue]")

        config_manager = init_config()
        config_manager.save_config()

        rprint("[green]✅ 配置文件初始化成功![/green]")
        rprint(f"[dim]配置文件位置: {config_manager.config_file}[/dim]")
        rprint(f"[dim]日志目录: {config_manager.config_dir / 'logs'}[/dim]")

    except Exception as e:
        rprint(f"[red]❌ 初始化配置失败: {e}[/red]")
        ctx.exit(1)