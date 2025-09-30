"""
API 客户端模块
"""

import httpx
import asyncio
import keyring
from typing import Dict, Any, Optional, List
from rich.console import Console
from .config import get_config
from .exceptions import APIError, AuthenticationError, ConnectionError
from ..models.responses import *

console = Console()


class APIClient:
    """GoodDEX API 客户端"""

    def __init__(self, base_url: Optional[str] = None):
        config = get_config()
        self.base_url = base_url or config.config.api.base_url
        self.timeout = config.config.api.timeout
        self.retry_count = config.config.api.retry_count
        self.verify_ssl = config.config.api.verify_ssl

        self.token: Optional[str] = None
        self.client: Optional[httpx.AsyncClient] = None

        # 从密钥环加载 token
        self.load_token()

    def load_token(self) -> None:
        """从密钥环加载访问令牌"""
        try:
            self.token = keyring.get_password("gooddex-cli", "access_token")
        except Exception as e:
            console.print(f"[yellow]⚠️  加载访问令牌失败: {e}[/yellow]")

    def save_token(self, token: str) -> None:
        """保存访问令牌到密钥环"""
        try:
            keyring.set_password("gooddex-cli", "access_token", token)
            self.token = token
        except Exception as e:
            console.print(f"[red]❌ 保存访问令牌失败: {e}[/red]")
            raise APIError(f"保存访问令牌失败: {e}")

    def clear_token(self) -> None:
        """清除访问令牌"""
        try:
            keyring.delete_password("gooddex-cli", "access_token")
            self.token = None
        except Exception:
            pass

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            verify=self.verify_ssl,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GoodDEX-CLI/1.0.0"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.client:
            await self.client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "GoodDEX-CLI/1.0.0"
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        require_auth: bool = False
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "GoodDEX-CLI/1.0.0"
        }

        if not self.client:
            raise ConnectionError("API 客户端未初始化")

        for attempt in range(self.retry_count + 1):
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=headers
                )

                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('detail', f"HTTP {response.status_code}")
                    except:
                        error_msg = f"HTTP {response.status_code}: {response.text}"

                    raise APIError(
                        error_msg,
                        status_code=response.status_code,
                        response_data=error_data if 'error_data' in locals() else None
                    )

                return response.json()

            except httpx.RequestError as e:
                if attempt == self.retry_count:
                    raise ConnectionError(f"连接失败: {e}")

                await asyncio.sleep(2 ** attempt)  # 指数退避

            except APIError:
                raise

            except Exception as e:
                if attempt == self.retry_count:
                    raise APIError(f"请求失败: {e}")

                await asyncio.sleep(2 ** attempt)

    # 认证相关 API
    async def login(self, username: str, password: str) -> AuthToken:
        """用户登录"""
        data = {"username": username, "password": password}
        response = await self._request("POST", "/api/auth/login", data=data, require_auth=False)

        token = response["access_token"]
        self.save_token(token)

        return AuthToken(**response)

    async def logout(self) -> None:
        """用户登出"""
        try:
            await self._request("POST", "/api/auth/logout")
        finally:
            self.clear_token()

    async def get_current_user(self) -> UserInfo:
        """获取当前用户信息"""
        response = await self._request("GET", "/api/auth/me")
        return UserInfo(**response)

    # 账户管理 API
    async def get_accounts(self, exchange: Optional[str] = None, is_active: Optional[bool] = None) -> List[Account]:
        """获取账户列表"""
        params = {}
        if exchange:
            params["exchange"] = exchange
        if is_active is not None:
            params["is_active"] = is_active

        response = await self._request("GET", "/api/accounts", params=params, require_auth=False)
        return [Account(**account) for account in response]

    async def create_account(self, account_data: Dict[str, Any]) -> Account:
        """创建账户 - 使用本地存储"""
        import json
        import os
        from datetime import datetime

        # 创建本地存储目录
        config = get_config()
        accounts_file = config.config_dir / "accounts.json"

        # 读取现有账户
        accounts = []
        if accounts_file.exists():
            try:
                with open(accounts_file, 'r', encoding='utf-8') as f:
                    accounts = json.load(f)
            except:
                accounts = []

        # 生成新账户ID
        next_id = max([acc.get('id', 0) for acc in accounts], default=0) + 1

        # 创建新账户
        new_account = {
            "id": next_id,
            "name": account_data["name"],
            "exchange": account_data["exchange"],
            "api_key": account_data["api_key"],
            "secret_key": account_data["secret_key"],
            "passphrase": account_data.get("passphrase"),
            "is_active": True,
            "is_testnet": account_data.get("is_testnet", False),
            "total_volume": 0.0,
            "total_trades": 0,
            "total_fees": 0.0,
            "created_at": datetime.now().isoformat()
        }

        # 添加到账户列表
        accounts.append(new_account)

        # 保存到文件
        os.makedirs(config.config_dir, exist_ok=True)
        with open(accounts_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)

        # 返回Account对象
        from ..models.responses import Account
        return Account(
            id=new_account["id"],
            name=new_account["name"],
            exchange=new_account["exchange"],
            is_active=new_account["is_active"],
            is_testnet=new_account["is_testnet"],
            total_volume=new_account["total_volume"],
            total_trades=new_account["total_trades"],
            total_fees=new_account["total_fees"],
            created_at=new_account["created_at"]
        )

    async def get_account_detail(self, account_id: int) -> AccountDetail:
        """获取账户详情"""
        response = await self._request("GET", f"/api/accounts/{account_id}")
        return AccountDetail(**response)

    async def update_account(self, account_id: int, update_data: Dict[str, Any]) -> Account:
        """更新账户"""
        response = await self._request("PUT", f"/api/accounts/{account_id}", data=update_data)
        return Account(**response)

    async def delete_account(self, account_id: int) -> None:
        """删除账户 - 使用本地存储"""
        import json

        config = get_config()
        accounts_file = config.config_dir / "accounts.json"

        if not accounts_file.exists():
            raise APIError("未找到账户数据文件")

        with open(accounts_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)

        # 查找并删除指定账户
        original_count = len(accounts)
        accounts = [acc for acc in accounts if acc['id'] != account_id]

        if len(accounts) == original_count:
            raise APIError(f"未找到账户ID {account_id}")

        # 保存更新后的账户列表
        with open(accounts_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)

    async def test_account_connection(self, account_id: int) -> Dict[str, Any]:
        """测试账户连接 - 真实API验证"""
        from .exchange_adapters import get_exchange_adapter
        import json

        try:
            # 读取账户信息
            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if not accounts_file.exists():
                return {"success": False, "message": "未找到账户数据文件"}

            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            # 查找指定账户
            account = None
            for acc in accounts:
                if acc['id'] == account_id:
                    account = acc
                    break

            if not account:
                return {"success": False, "message": f"未找到账户ID {account_id}"}

            # 创建交易所适配器并测试连接
            adapter = get_exchange_adapter(
                exchange=account['exchange'],
                api_key=account['api_key'],
                secret=account['secret_key'],
                passphrase=account.get('passphrase'),
                testnet=account.get('is_testnet', False)
            )

            # 执行真实的连接测试
            result = await adapter.test_connection()

            # 关闭适配器会话（如果有）
            if hasattr(adapter, 'close'):
                await adapter.close()

            return result

        except Exception as e:
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}"
            }

    async def get_account_balances(self, account_id: int, refresh: bool = False) -> List[Dict[str, Any]]:
        """获取账户余额 - 真实API调用"""
        from .exchange_adapters import get_exchange_adapter
        import json

        try:
            # 读取账户信息
            config = get_config()
            accounts_file = config.config_dir / "accounts.json"

            if not accounts_file.exists():
                raise APIError("未找到账户数据文件")

            with open(accounts_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

            # 查找指定账户
            account = None
            for acc in accounts:
                if acc['id'] == account_id:
                    account = acc
                    break

            if not account:
                raise APIError(f"未找到账户ID {account_id}")

            # 创建交易所适配器并获取余额
            adapter = get_exchange_adapter(
                exchange=account['exchange'],
                api_key=account['api_key'],
                secret=account['secret_key'],
                passphrase=account.get('passphrase'),
                testnet=account.get('is_testnet', False)
            )

            # 获取真实余额数据
            balances = await adapter.get_balance()

            # 关闭适配器会话（如果有）
            if hasattr(adapter, 'close'):
                await adapter.close()

            return balances

        except Exception as e:
            raise APIError(f"获取余额失败: {str(e)}")

    # 交易管理 API
    async def get_trading_sessions(self, status_filter: Optional[str] = None) -> List[TradingSession]:
        """获取交易会话列表"""
        params = {}
        if status_filter:
            params["status_filter"] = status_filter

        response = await self._request("GET", "/api/trading/sessions", params=params)
        return [TradingSession(**session) for session in response]

    async def create_trading_session(self, session_data: Dict[str, Any]) -> TradingSession:
        """创建交易会话"""
        response = await self._request("POST", "/api/trading/sessions", data=session_data)
        return TradingSession(**response)

    async def get_trading_session(self, session_id: int) -> TradingSession:
        """获取交易会话详情"""
        response = await self._request("GET", f"/api/trading/sessions/{session_id}")
        return TradingSession(**response)

    async def start_trading_session(self, session_id: int) -> Dict[str, Any]:
        """启动交易会话"""
        return await self._request("POST", f"/api/trading/sessions/{session_id}/start")

    async def close_trading_session(self, session_id: int) -> Dict[str, Any]:
        """关闭交易会话"""
        return await self._request("POST", f"/api/trading/sessions/{session_id}/close")

    async def get_session_trades(self, session_id: int) -> List[Trade]:
        """获取交易会话的交易记录"""
        response = await self._request("GET", f"/api/trading/sessions/{session_id}/trades")
        return [Trade(**trade) for trade in response]

    async def get_account_positions(self, account_id: int) -> Dict[str, Any]:
        """获取账户持仓"""
        return await self._request("GET", f"/api/trading/positions/{account_id}")

    # 统计数据 API
    async def get_trading_overview(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> TradingOverview:
        """获取交易概览"""
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = await self._request("GET", "/api/statistics/overview", params=params)
        return TradingOverview(**response)

    async def get_volume_statistics(
        self,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30
    ) -> List[VolumeStatistics]:
        """获取交易量统计"""
        params = {"period": period, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = await self._request("GET", "/api/statistics/volume", params=params)
        return [VolumeStatistics(**stat) for stat in response]

    async def get_pnl_statistics(
        self,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30
    ) -> List[PnLStatistics]:
        """获取盈亏统计"""
        params = {"period": period, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = await self._request("GET", "/api/statistics/pnl", params=params)
        return [PnLStatistics(**stat) for stat in response]

    async def get_fee_statistics(
        self,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30
    ) -> List[FeeStatistics]:
        """获取手续费统计"""
        params = {"period": period, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = await self._request("GET", "/api/statistics/fees", params=params)
        return [FeeStatistics(**stat) for stat in response]

    # 系统 API
    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        return await self._request("GET", "/api/health", require_auth=False)


# 全局 API 客户端实例
_api_client: Optional[APIClient] = None


def get_api_client(base_url: Optional[str] = None) -> APIClient:
    """获取 API 客户端实例"""
    global _api_client
    if _api_client is None:
        _api_client = APIClient(base_url)
    return _api_client