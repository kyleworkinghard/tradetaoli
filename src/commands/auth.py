"""
认证管理命令
"""

import click
import asyncio
import getpass
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from ..core.api_client import get_api_client
from ..core.exceptions import APIError, AuthenticationError

console = Console()


@click.group()
def auth_group():
    """🔐 认证管理"""
    pass


@auth_group.command()
@click.option('--username', '-u', prompt=True, help='用户名')
@click.option('--password', '-p', help='密码 (留空则提示输入)')
@click.pass_context
def login(ctx, username: str, password: str):
    """登录系统"""
    if not password:
        password = getpass.getpass("密码: ")

    async def _login():
        try:
            async with get_api_client() as client:
                rprint("[blue]🔐 正在登录...[/blue]")

                token_info = await client.login(username, password)

                rprint(f"[green]✅ 登录成功![/green]")
                rprint(f"[dim]令牌类型: {token_info.token_type}[/dim]")
                rprint(f"[dim]有效期: {token_info.expires_in} 秒[/dim]")

                # 获取用户信息
                user_info = await client.get_current_user()
                rprint(f"[blue]👋 欢迎, {user_info.username}![/blue]")

        except AuthenticationError as e:
            rprint(f"[red]❌ 认证失败: {e}[/red]")
            ctx.exit(1)
        except APIError as e:
            rprint(f"[red]❌ API 错误: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 登录失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_login())


@auth_group.command()
@click.pass_context
def logout(ctx):
    """登出系统"""
    async def _logout():
        try:
            async with get_api_client() as client:
                rprint("[blue]🔓 正在登出...[/blue]")
                await client.logout()
                rprint("[green]✅ 已成功登出[/green]")

        except Exception as e:
            rprint(f"[yellow]⚠️  登出时发生错误: {e}[/yellow]")
            rprint("[green]✅ 本地令牌已清除[/green]")

    asyncio.run(_logout())


@auth_group.command()
@click.pass_context
def status(ctx):
    """查看登录状态"""
    async def _status():
        try:
            async with get_api_client() as client:
                if not client.token:
                    rprint("[yellow]❌ 未登录[/yellow]")
                    rprint("[dim]使用 'gooddex auth login' 登录[/dim]")
                    return

                rprint("[blue]🔍 检查登录状态...[/blue]")
                user_info = await client.get_current_user()

                # 创建状态表格
                table = Table(title="🔐 登录状态", show_header=False)
                table.add_column("项目", style="cyan")
                table.add_column("值", style="white")

                table.add_row("状态", "[green]✅ 已登录[/green]")
                table.add_row("用户名", user_info.username)
                table.add_row("邮箱", user_info.email)
                table.add_row("用户ID", str(user_info.id))
                table.add_row("账户状态", "[green]活跃[/green]" if user_info.is_active else "[red]未激活[/red]")
                table.add_row("注册时间", user_info.created_at.strftime("%Y-%m-%d %H:%M:%S"))

                console.print(table)

        except AuthenticationError:
            rprint("[yellow]❌ 登录已过期[/yellow]")
            rprint("[dim]使用 'gooddex auth login' 重新登录[/dim]")
        except APIError as e:
            rprint(f"[red]❌ API 错误: {e}[/red]")
        except Exception as e:
            rprint(f"[red]❌ 检查状态失败: {e}[/red]")

    asyncio.run(_status())


@auth_group.command()
@click.option('--username', '-u', prompt=True, help='用户名')
@click.option('--email', '-e', prompt=True, help='邮箱地址')
@click.option('--password', '-p', help='密码 (留空则提示输入)')
@click.option('--confirm-password', help='确认密码 (留空则提示输入)')
@click.pass_context
def register(ctx, username: str, email: str, password: str, confirm_password: str):
    """注册新用户"""
    if not password:
        password = getpass.getpass("密码: ")

    if not confirm_password:
        confirm_password = getpass.getpass("确认密码: ")

    if password != confirm_password:
        rprint("[red]❌ 密码不一致[/red]")
        ctx.exit(1)

    async def _register():
        try:
            async with get_api_client() as client:
                rprint("[blue]📝 正在注册用户...[/blue]")

                # 注册用户
                register_data = {
                    "username": username,
                    "email": email,
                    "password": password
                }

                response = await client._request(
                    "POST",
                    "/api/auth/register",
                    data=register_data,
                    require_auth=False
                )

                rprint(f"[green]✅ 注册成功![/green]")
                rprint(f"[blue]用户名: {response['username']}[/blue]")
                rprint(f"[blue]邮箱: {response['email']}[/blue]")
                rprint(f"[dim]现在可以使用 'gooddex auth login' 登录[/dim]")

        except APIError as e:
            rprint(f"[red]❌ 注册失败: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 注册失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_register())