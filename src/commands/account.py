"""
账户管理命令
"""

import click
import asyncio
import getpass
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from typing import Optional

from ..core.api_client import get_api_client
from ..core.exceptions import APIError, AuthenticationError
from ..models.responses import ExchangeType

console = Console()


@click.group()
def account_group():
    """💰 账户管理"""
    pass


@account_group.command()
@click.option('--exchange', type=click.Choice(['aster', 'okx']), help='按交易所筛选')
@click.option('--active-only', is_flag=True, help='只显示活跃账户')
@click.pass_context
def list(ctx, exchange: Optional[str], active_only: bool):
    """列出所有账户"""
    try:
        console.print("[blue]📋 获取账户列表...[/blue]")

        # 加载账户数据
        import json
        from pathlib import Path
        from datetime import datetime

        config_dir = Path.home() / ".gooddex"
        accounts_file = config_dir / "accounts.json"

        if not accounts_file.exists():
            console.print("[yellow]⚠️ 还没有添加任何账户[/yellow]")
            return

        with open(accounts_file, 'r') as f:
            accounts = json.load(f)

        if not accounts:
            console.print("[yellow]⚠️ 还没有添加任何账户[/yellow]")
            return

        # 按条件筛选
        if exchange:
            accounts = [acc for acc in accounts if acc.get('exchange') == exchange]
        if active_only:
            accounts = [acc for acc in accounts if acc.get('is_active', True)]

        # 显示账户列表
        console.print(f"\n[green]✅ 找到 {len(accounts)} 个账户[/green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=6)
        table.add_column("账户名", min_width=20)
        table.add_column("交易所", min_width=12)
        table.add_column("状态", min_width=8)
        table.add_column("创建时间", min_width=20)

        for account in accounts:
            # 安全获取字段，提供默认值
            account_id = str(account.get("id", "N/A"))
            name = account.get("name", "未知")
            exchange = account.get("exchange", "未知").upper()

            # 处理状态字段 - 如果没有is_active字段，默认为活跃
            status = "🟢 活跃" if account.get("is_active", True) else "🔴 禁用"

            # 处理创建时间
            created_at = account.get("created_at", "未知")
            if created_at != "未知":
                try:
                    # 尝试格式化时间
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_at = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    # 如果时间格式有问题，保持原样
                    pass

            table.add_row(
                account_id,
                name,
                exchange,
                status,
                created_at
            )

        console.print(table)
        console.print(f"\n[dim]💡 使用 'gdx account test <ID>' 测试账户连接[/dim]")

    except Exception as e:
        console.print(f"[red]❌ 获取账户列表失败: {e}[/red]")


@account_group.command()
@click.option('--name', '-n', required=True, help='账户名称')
@click.option('--exchange', '-e', required=True, type=click.Choice(['aster', 'okx']), help='交易所类型')
@click.option('--api-key', required=True, help='API 密钥')
@click.option('--secret', help='Secret 密钥 (留空则提示输入)')
@click.option('--passphrase', help='Passphrase (OKX 需要)')
@click.option('--testnet', is_flag=True, help='是否为测试网')
@click.pass_context
def add(ctx, name: str, exchange: str, api_key: str, secret: str, passphrase: str, testnet: bool):
    """添加新账户"""
    if not secret:
        secret = getpass.getpass("Secret 密钥: ")

    if exchange == 'okx' and not passphrase:
        passphrase = getpass.getpass("Passphrase: ")

    async def _add():
        try:
            async with get_api_client() as client:
                rprint(f"[blue]➕ 正在添加 {exchange.upper()} 账户...[/blue]")

                account_data = {
                    "name": name,
                    "exchange": exchange,
                    "api_key": api_key,
                    "secret_key": secret,
                    "is_testnet": testnet
                }

                if passphrase:
                    account_data["passphrase"] = passphrase

                account = await client.create_account(account_data)

                rprint(f"[green]✅ 账户添加成功![/green]")
                rprint(f"[blue]账户ID: {account.id}[/blue]")
                rprint(f"[blue]账户名称: {account.name}[/blue]")
                rprint(f"[blue]交易所: {account.exchange.upper()}[/blue]")

                # 测试连接
                rprint(f"[blue]🔍 测试账户连接...[/blue]")
                try:
                    test_result = await client.test_account_connection(account.id)
                    if test_result.get('success'):
                        rprint(f"[green]✅ 连接测试成功[/green]")
                    else:
                        rprint(f"[yellow]⚠️  连接测试失败: {test_result.get('message', '未知错误')}[/yellow]")
                except:
                    rprint(f"[yellow]⚠️  无法测试连接[/yellow]")

        except APIError as e:
            rprint(f"[red]❌ 添加账户失败: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 添加账户失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_add())


@account_group.command()
@click.option('--id', 'account_id', type=int, help='账户ID')
@click.option('--name', help='账户名称 (二选一)')
@click.pass_context
def balance(ctx, account_id: Optional[int], name: Optional[str]):
    """查看账户余额"""
    if not account_id and not name:
        rprint("[red]❌ 请指定账户ID或名称[/red]")
        ctx.exit(1)

    async def _balance():
        try:
            # 从本地文件读取账户数据
            import json
            from ..core.config import get_config

            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if not accounts_file.exists():
                rprint("[red]❌ 未找到账户数据[/red]")
                ctx.exit(1)

            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            # 确定要查询的账户ID
            target_account_id = account_id
            if name and not account_id:
                matching_accounts = [acc for acc in accounts if acc['name'] == name]
                if not matching_accounts:
                    rprint(f"[red]❌ 未找到名称为 '{name}' 的账户[/red]")
                    ctx.exit(1)
                if len(matching_accounts) > 1:
                    rprint(f"[yellow]⚠️  找到多个名称为 '{name}' 的账户，请使用账户ID[/yellow]")
                    for acc in matching_accounts:
                        rprint(f"  ID: {acc['id']}, 交易所: {acc['exchange']}")
                    ctx.exit(1)
                target_account_id = matching_accounts[0]['id']

            # 查找指定账户
            target_account = None
            for acc in accounts:
                if acc['id'] == target_account_id:
                    target_account = acc
                    break

            if not target_account:
                rprint(f"[red]❌ 未找到账户ID {target_account_id}[/red]")
                ctx.exit(1)

            rprint(f"[blue]💰 获取账户 {target_account_id} 余额...[/blue]")

            # 使用真实API获取余额
            async with get_api_client() as client:
                try:
                    balances = await client.get_account_balances(target_account_id)

                    rprint(f"[green]📋 账户信息[/green]")
                    rprint(f"名称: {target_account['name']}")
                    rprint(f"交易所: {target_account['exchange'].upper()}")
                    rprint(f"连接状态: [green]✅ 连接正常[/green]")

                    from datetime import datetime
                    rprint(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    if not balances:
                        rprint("[yellow]📭 暂无余额数据[/yellow]")
                        return

                    # 创建余额表格
                    table = Table(title=f"💰 账户余额 - {target_account['name']}")
                    table.add_column("币种", style="cyan")
                    table.add_column("可用余额", justify="right", style="green")
                    table.add_column("冻结余额", justify="right", style="yellow")
                    table.add_column("总余额", justify="right", style="white")

                    for balance in balances:
                        if balance["total_balance"] > 0:  # 只显示有余额的币种
                            table.add_row(
                                balance["currency"],
                                f"{balance['free_balance']:.8f}",
                                f"{balance['used_balance']:.8f}",
                                f"{balance['total_balance']:.8f}"
                            )

                    console.print(table)

                except Exception as e:
                    rprint(f"[red]❌ 获取余额失败: {str(e)}[/red]")
                    rprint(f"[yellow]⚠️  请检查账户API配置是否正确[/yellow]")
                    ctx.exit(1)

        except APIError as e:
            rprint(f"[red]❌ API 错误: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 获取余额失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_balance())


@account_group.command()
@click.option('--id', 'account_id', type=int, help='账户ID')
@click.option('--name', help='账户名称 (二选一)')
@click.pass_context
def test(ctx, account_id: Optional[int], name: Optional[str]):
    """测试账户连接"""
    if not account_id and not name:
        rprint("[red]❌ 请指定账户ID或名称[/red]")
        ctx.exit(1)

    async def _test():
        try:
            # 从本地文件读取账户数据
            import json
            from ..core.config import get_config

            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if not accounts_file.exists():
                rprint("[red]❌ 未找到账户数据[/red]")
                ctx.exit(1)

            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            # 确定要测试的账户ID
            target_account_id = account_id
            if name and not account_id:
                matching_accounts = [acc for acc in accounts if acc['name'] == name]
                if not matching_accounts:
                    rprint(f"[red]❌ 未找到名称为 '{name}' 的账户[/red]")
                    ctx.exit(1)
                target_account_id = matching_accounts[0]['id']

            # 查找指定账户
            target_account = None
            for acc in accounts:
                if acc['id'] == target_account_id:
                    target_account = acc
                    break

            if not target_account:
                rprint(f"[red]❌ 未找到账户ID {target_account_id}[/red]")
                ctx.exit(1)

            rprint(f"[blue]🔍 测试账户 {target_account_id} 连接...[/blue]")

            # 使用真实API进行连接测试
            async with get_api_client() as client:
                try:
                    test_result = await client.test_account_connection(target_account_id)

                    if test_result.get('success'):
                        rprint(f"[green]✅ 连接测试成功[/green]")
                        rprint(f"[dim]{test_result.get('message', '连接正常')}[/dim]")

                        # 显示账户类型信息
                        if 'account_type' in test_result:
                            rprint(f"[blue]账户类型: {test_result['account_type']}[/blue]")

                        # 显示持仓数量（如果是OKX）
                        if 'positions_count' in test_result:
                            rprint(f"[blue]持仓数量: {test_result['positions_count']}[/blue]")

                        # 显示账户ID（如果是Aster）
                        if 'account_id' in test_result:
                            rprint(f"[blue]账户ID: {test_result['account_id']}[/blue]")

                        rprint(f"[green]💰 账户API连接正常[/green]")
                    else:
                        rprint(f"[red]❌ 连接测试失败[/red]")
                        rprint(f"[red]{test_result.get('message', '未知错误')}[/red]")
                        ctx.exit(1)

                except Exception as e:
                    rprint(f"[red]❌ 连接测试失败: {str(e)}[/red]")
                    rprint(f"[yellow]⚠️  请检查账户API配置是否正确[/yellow]")
                    ctx.exit(1)

        except APIError as e:
            rprint(f"[red]❌ API 错误: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 测试连接失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_test())


@account_group.command()
@click.option('--id', 'account_id', required=True, type=int, help='账户ID')
@click.option('--name', help='新的账户名称')
@click.option('--active/--inactive', default=None, help='启用或停用账户')
@click.pass_context
def update(ctx, account_id: int, name: Optional[str], active: Optional[bool]):
    """更新账户信息"""
    if not name and active is None:
        rprint("[red]❌ 请指定要更新的内容[/red]")
        ctx.exit(1)

    async def _update():
        try:
            async with get_api_client() as client:
                rprint(f"[blue]✏️  更新账户 {account_id}...[/blue]")

                update_data = {}
                if name:
                    update_data["name"] = name
                if active is not None:
                    update_data["is_active"] = active

                account = await client.update_account(account_id, update_data)

                rprint(f"[green]✅ 账户更新成功![/green]")
                rprint(f"[blue]账户名称: {account.name}[/blue]")
                rprint(f"[blue]状态: {'活跃' if account.is_active else '停用'}[/blue]")

        except APIError as e:
            rprint(f"[red]❌ 更新账户失败: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 更新账户失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_update())


@account_group.command()
@click.option('--id', 'account_id', required=True, type=int, help='账户ID')
@click.confirmation_option(prompt='确定要删除此账户吗？')
@click.pass_context
def delete(ctx, account_id: int):
    """删除账户"""
    async def _delete():
        try:
            async with get_api_client() as client:
                rprint(f"[blue]🗑️  删除账户 {account_id}...[/blue]")

                await client.delete_account(account_id)

                rprint(f"[green]✅ 账户删除成功![/green]")

        except APIError as e:
            rprint(f"[red]❌ 删除账户失败: {e}[/red]")
            ctx.exit(1)
        except Exception as e:
            rprint(f"[red]❌ 删除账户失败: {e}[/red]")
            ctx.exit(1)

    asyncio.run(_delete())


@account_group.command()
@click.option('--name', '-n', required=True, help='账户名称')
@click.option('--api-key', required=True, help='API Key')
@click.option('--secret', required=True, help='Secret Key (Base64 Ed25519私钥)')
@click.option('--testnet', is_flag=True, help='是否为测试网')
def add_backpack(name: str, api_key: str, secret: str, testnet: bool):
    """添加Backpack账户"""
    try:
        import json
        from pathlib import Path
        from datetime import datetime
        
        account_data = {
            "name": name,
            "exchange": "backpack",
            "api_key": api_key,
            "secret": secret,
            "testnet": testnet,
            "created_at": datetime.now().isoformat()
        }

        # 保存到accounts.json
        config_dir = Path.home() / ".gooddex"
        config_dir.mkdir(exist_ok=True)
        accounts_file = config_dir / "accounts.json"

        if accounts_file.exists():
            with open(accounts_file, 'r') as f:
                accounts = json.load(f)
        else:
            accounts = []

        # 分配账户ID
        account_data["id"] = len(accounts) + 1
        accounts.append(account_data)

        with open(accounts_file, 'w') as f:
            json.dump(accounts, f, indent=2)

        console.print(f"[green]✅ Backpack账户添加成功[/green]")
        console.print(f"账户ID: {account_data['id']}")
        console.print(f"账户名: {name}")
        console.print(f"交易所: Backpack")

    except Exception as e:
        console.print(f"[red]❌ 添加Backpack账户失败: {e}[/red]")