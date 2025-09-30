"""
Backpack Exchange Adapter - 基于官方实现的签名机制
"""
import time
import base64
import json
import httpx
from typing import Dict, Any, List, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from rich.console import Console

console = Console()


class BackpackAdapter:
    """Backpack交易所适配器"""

    BASE_URL = "https://api.backpack.exchange/"

    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        """
        初始化Backpack适配器

        :param api_key: API密钥 (Base64编码的Ed25519公钥)
        :param secret_key: 私钥 (Base64编码的Ed25519私钥)
        :param testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.testnet = testnet
        self.window = 5000  # 请求有效时间窗口（毫秒）
        self.session = None

        # 初始化Ed25519私钥
        try:
            private_key_bytes = base64.b64decode(secret_key)
            self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            console.print("[green]✅ Backpack私钥初始化成功[/green]")
        except Exception as e:
            console.print(f"[red]❌ Backpack私钥初始化失败: {e}[/red]")
            self.private_key = None

    async def _init_session(self):
        """初始化HTTP会话"""
        if not self.session:
            self.session = httpx.AsyncClient(timeout=30)

    def _generate_signature(self, action: str, timestamp: int, params: Optional[Dict] = None) -> Dict[str, str]:
        """
        生成请求签名

        签名格式: instruction={action}{params}&timestamp={timestamp}&window={window}
        """
        if not self.private_key:
            raise ValueError("私钥未初始化")

        # 处理参数
        if params:
            params_copy = params.copy()
            # 布尔值转换为小写字符串
            for key, value in params_copy.items():
                if isinstance(value, bool):
                    params_copy[key] = str(value).lower()

            # 构建参数字符串
            param_str = "&" + "&".join(f"{k}={v}" for k, v in sorted(params_copy.items()))
        else:
            param_str = ""

        # 确保 param_str 为空时不影响签名格式
        if not param_str:
            param_str = ""

        # 构建签名字符串
        sign_str = f"instruction={action}{param_str}&timestamp={timestamp}&window={self.window}"

        # Ed25519签名
        signature = base64.b64encode(self.private_key.sign(sign_str.encode())).decode()

        return {
            "X-API-Key": self.api_key,
            "X-Signature": signature,
            "X-Timestamp": str(timestamp),
            "X-Window": str(self.window),
            "Content-Type": "application/json; charset=utf-8"
        }

    async def _send_request(self, method: str, endpoint: str, action: str = None, params: Dict = None) -> Any:
        """
        发送API请求

        :param method: HTTP方法 (GET, POST, DELETE, etc.)
        :param endpoint: API端点
        :param action: 签名action名称（私有API需要）
        :param params: 请求参数
        """
        await self._init_session()

        url = f"{self.BASE_URL}{endpoint}"

        # 公开API不需要签名
        if action is None:
            if method == "GET":
                response = await self.session.get(url, params=params)
            else:
                response = await self.session.post(url, json=params)
        else:
            # 私有API需要签名
            timestamp = int(time.time() * 1000)
            headers = self._generate_signature(action, timestamp, params)

            if method == "GET":
                response = await self.session.get(url, headers=headers, params=params)
            elif method == "DELETE":
                response = await self.session.delete(url, headers=headers, json=params)
            elif method == "PATCH":
                response = await self.session.patch(url, headers=headers, json=params)
            elif method == "PUT":
                response = await self.session.put(url, headers=headers, json=params)
            else:  # POST
                response = await self.session.post(url, headers=headers, json=params)

        # 处理响应
        if 200 <= response.status_code < 300:
            if response.status_code == 204:
                return None
            try:
                return response.json()
            except ValueError:
                return response.text
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                error = response.json()
                error_msg = f"{error.get('code', '')} - {error.get('message', '')}"
            except:
                error_msg = f"{response.status_code}: {response.text[:200]}"

            console.print(f"[red]API错误: {error_msg}[/red]")
            raise Exception(f"API Error: {error_msg}")

    # ============== 公开API ==============

    async def get_markets(self) -> List[Dict]:
        """获取所有支持的市场"""
        return await self._send_request("GET", "api/v1/markets")

    async def get_assets(self) -> List[Dict]:
        """获取所有支持的资产"""
        return await self._send_request("GET", "api/v1/assets")

    async def get_ticker(self, symbol: str) -> Dict:
        """获取交易对行情"""
        return await self._send_request("GET", "api/v1/ticker", params={"symbol": symbol})

    async def get_depth(self, symbol: str, limit: int = 20) -> Dict:
        """获取盘口深度"""
        params = {"symbol": symbol}
        if limit:
            params["limit"] = limit
        return await self._send_request("GET", "api/v1/depth", params=params)

    async def get_klines(self, symbol: str, interval: str, start_time: int = None, end_time: int = None) -> List:
        """获取K线数据"""
        params = {"symbol": symbol, "interval": interval}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._send_request("GET", "api/v1/klines", params=params)

    async def get_status(self) -> Dict:
        """获取系统状态"""
        return await self._send_request("GET", "api/v1/status")

    async def get_ping(self) -> int:
        """测试连接"""
        return await self._send_request("GET", "api/v1/ping")

    async def get_time(self) -> int:
        """获取服务器时间"""
        return await self._send_request("GET", "api/v1/time")

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List:
        """获取最近成交"""
        params = {"symbol": symbol, "limit": limit}
        return await self._send_request("GET", "api/v1/trades", params=params)

    async def get_historical_trades(self, symbol: str, limit: int = 100, offset: int = 0) -> List:
        """获取历史成交"""
        params = {"symbol": symbol, "limit": limit, "offset": offset}
        return await self._send_request("GET", "api/v1/trades/history", params=params)

    # ============== 私有API ==============

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            await self._init_session()

            # 测试公开端点
            server_time = await self.get_time()

            # 测试私有端点
            try:
                account = await self.get_account()
                return {
                    "success": True,
                    "message": "Backpack连接成功（认证通过）",
                    "server_time": server_time
                }
            except:
                return {
                    "success": True,
                    "message": "Backpack连接成功（认证失败）",
                    "server_time": server_time
                }
        except Exception as e:
            return {"success": False, "message": f"连接错误: {str(e)}"}

    async def get_account(self) -> Dict:
        """获取账户信息"""
        return await self._send_request("GET", "api/v1/account", "accountQuery")

    async def update_account(self, **kwargs) -> None:
        """更新账户设置"""
        return await self._send_request("PATCH", "api/v1/account", "accountUpdate", kwargs)

    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取账户余额"""
        try:
            data = await self._send_request("GET", "api/v1/capital", "balanceQuery")

            # 转换为统一格式
            balances = []
            if isinstance(data, list):
                for item in data:
                    available = float(item.get("available", 0))
                    locked = float(item.get("locked", 0))
                    if available > 0 or locked > 0:
                        balances.append({
                            "currency": item.get("symbol", ""),
                            "free_balance": available,
                            "used_balance": locked,
                            "total_balance": available + locked
                        })
            elif isinstance(data, dict):
                for symbol, balance_info in data.items():
                    if isinstance(balance_info, dict):
                        available = float(balance_info.get("available", 0))
                        locked = float(balance_info.get("locked", 0))
                        if available > 0 or locked > 0:
                            balances.append({
                                "currency": symbol,
                                "free_balance": available,
                                "used_balance": locked,
                                "total_balance": available + locked
                            })

            return balances
        except Exception as e:
            console.print(f"[red]获取余额失败: {e}[/red]")
            return []

    async def get_deposits(self, limit: int = 100, offset: int = 0) -> List:
        """获取充值历史"""
        params = {"limit": limit, "offset": offset}
        return await self._send_request("GET", "api/v1/deposits", "depositQueryAll", params)

    async def get_deposit_address(self, blockchain: str) -> Dict:
        """获取充值地址"""
        params = {"blockchain": blockchain}
        return await self._send_request("GET", "api/v1/deposit/address", "depositAddressQuery", params)

    async def get_withdrawals(self, limit: int = 100, offset: int = 0) -> List:
        """获取提现历史"""
        params = {"limit": limit, "offset": offset}
        return await self._send_request("GET", "api/v1/withdrawals", "withdrawalQueryAll", params)

    async def request_withdrawal(self, address: str, blockchain: str, quantity: str, symbol: str, **kwargs) -> str:
        """发起提现"""
        params = {
            "address": address,
            "blockchain": blockchain,
            "quantity": quantity,
            "symbol": symbol
        }
        params.update(kwargs)
        return await self._send_request("POST", "api/v1/withdraw", "withdraw", params)

    async def get_order_history(self, symbol: str = None, limit: int = 100, offset: int = 0) -> List:
        """获取订单历史"""
        params = {"limit": limit, "offset": offset}
        if symbol:
            params["symbol"] = symbol
        return await self._send_request("GET", "api/v1/orders/history", "orderHistoryQueryAll", params)

    async def get_fill_history(self, symbol: str = None, limit: int = 100, offset: int = 0) -> List:
        """获取成交历史"""
        params = {"limit": limit, "offset": offset}
        if symbol:
            params["symbol"] = symbol
        return await self._send_request("GET", "api/v1/fills", "fillHistoryQueryAll", params)

    async def get_open_orders(self, symbol: str = None) -> List:
        """获取当前挂单"""
        params = {"symbol": symbol} if symbol else {}
        return await self._send_request("GET", "api/v1/orders", "orderQueryAll", params)

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓"""
        try:
            data = await self._send_request("GET", "api/v1/position", "positionQuery")

            # 转换为统一格式
            positions = []
            if isinstance(data, list):
                for pos in data:
                    size = float(pos.get("size", 0))
                    if abs(size) > 0:
                        positions.append({
                            "symbol": pos.get("symbol"),
                            "side": "long" if size > 0 else "short",
                            "size": abs(size),
                            "entry_price": float(pos.get("entryPrice", 0)),
                            "mark_price": float(pos.get("markPrice", 0)),
                            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                            "percentage": float(pos.get("percentage", 0))
                        })

            return positions
        except Exception as e:
            console.print(f"[red]获取持仓失败: {e}[/red]")
            return []

    async def _adjust_price_for_backpack(self, symbol: str, price: float, side: str) -> float:
        """调整价格以符合Backpack的价格验证规则"""
        try:
            # 获取ticker价格作为参考
            ticker = await self.get_ticker(symbol)
            last_price = float(ticker.get('lastPrice', price))

            # Backpack价格限制：75%-125%的参考价格
            min_price = last_price * 0.76  # 稍微保守一点
            max_price = last_price * 1.24  # 稍微保守一点

            # 确保价格在允许范围内
            if price < min_price:
                adjusted_price = min_price
            elif price > max_price:
                adjusted_price = max_price
            else:
                adjusted_price = price

            # 确保价格符合tickSize (0.1)
            adjusted_price = round(adjusted_price, 1)

            console.print(f"[dim]参考价格: {last_price}, 允许范围: {min_price:.1f} - {max_price:.1f}[/dim]")

            return adjusted_price

        except Exception as e:
            console.print(f"[yellow]价格调整失败，使用原价格: {e}[/yellow]")
            return round(price, 1) if price else 0.0

    async def place_order(self,
                          symbol: str,
                          side: str,
                          amount: float,
                          price: float = None,
                          order_type: str = "limit",
                          **kwargs) -> Dict[str, Any]:
        """下单"""
        try:
            params = {
                "orderType": "Limit" if order_type.lower() == "limit" else "Market",
                "side": "Bid" if side.lower() == "buy" else "Ask",
                "symbol": symbol
            }

            if order_type.lower() == "limit":
                # 对于限价单，使用Backpack价格验证规则调整价格
                adjusted_price = await self._adjust_price_for_backpack(symbol, price, side)
                params["price"] = str(adjusted_price)
                params["quantity"] = str(amount)
                # 默认使用GTC
                params["timeInForce"] = kwargs.get("timeInForce", "GTC")

                console.print(f"[yellow]🔍 Backpack价格调整:[/yellow]")
                console.print(f"  原始价格: {price}")
                console.print(f"  调整后价格: {adjusted_price}")
            else:
                params["quantity"] = str(amount)

            # 添加其他参数
            for key, value in kwargs.items():
                if key not in params:
                    params[key] = value

            result = await self._send_request("POST", "api/v1/order", "orderExecute", params)

            # 转换为统一格式
            return {
                "order_id": result.get("id", result.get("orderId")),
                "symbol": result.get("symbol"),
                "side": side,
                "amount": amount,
                "price": price,
                "status": result.get("status", "new"),
                "type": "backpack_order"
            }
        except Exception as e:
            console.print(f"[red]Backpack下单失败: {e}[/red]")
            return {}

    async def cancel_order(self, order_id: str, symbol: str = None) -> bool:
        """撤单"""
        try:
            params = {"orderId": order_id}
            if symbol:
                params["symbol"] = symbol

            await self._send_request("DELETE", "api/v1/order", "orderCancel", params)
            return True
        except Exception as e:
            console.print(f"[red]撤单失败: {e}[/red]")
            return False

    async def cancel_all_orders(self, symbol: str) -> int:
        """撤销所有订单"""
        params = {"symbol": symbol}
        result = await self._send_request("DELETE", "api/v1/orders", "orderCancelAllBySymbol", params)
        return result.get("cancelledOrdersCount", 0)

    async def get_order_status(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
        """获取订单状态"""
        try:
            params = {"orderId": order_id}
            if symbol:
                params["symbol"] = symbol

            data = await self._send_request("GET", "api/v1/order", "orderQuery", params)

            # 转换为统一格式
            return {
                "order_id": data.get("id", order_id),
                "status": data.get("status", "").lower(),
                "filled": float(data.get("filledQuantity", 0)),
                "amount": float(data.get("quantity", 0)),
                "remaining": float(data.get("quantity", 0)) - float(data.get("filledQuantity", 0))
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """获取盘口深度（统一接口）"""
        try:
            data = await self.get_depth(symbol, depth)

            # 检查盘口数据质量
            raw_bids = data.get("bids", [])
            raw_asks = data.get("asks", [])

            if raw_bids and raw_asks:
                # 🔧 修复Backpack的bids排序问题
                # Backpack返回的bids不是按价格降序排列，需要手动排序
                sorted_bids = sorted(raw_bids, key=lambda x: float(x[0]), reverse=True)

                # asks通常是正确的升序，但也检查一下
                sorted_asks = sorted(raw_asks, key=lambda x: float(x[0]))

                best_bid = float(sorted_bids[0][0])
                best_ask = float(sorted_asks[0][0])
                spread = best_ask - best_bid
                spread_pct = abs(spread) / best_ask * 100

                console.print(f"[dim]Backpack盘口修复: 买价${best_bid:,.2f}, 卖价${best_ask:,.2f}, 价差${spread:+.2f}[/dim]")

                # 如果价差仍然异常(>1%)，使用ticker价格
                if spread_pct > 1.0 or spread < -100:  # 负价差太大也异常
                    console.print(f"[yellow]⚠️ Backpack盘口仍异常(价差{spread:+.2f})，使用ticker价格[/yellow]")
                    ticker = await self.get_ticker(symbol)
                    last_price = float(ticker.get('lastPrice', best_ask))

                    # 生成合理的盘口价格（围绕lastPrice的小价差）
                    tick_size = 0.1  # BTC_USDC_PERP的tickSize
                    synthetic_bid = round(last_price - tick_size, 1)
                    synthetic_ask = round(last_price + tick_size, 1)

                    return {
                        "symbol": symbol,
                        "bids": [[synthetic_bid, 1.0]],  # 使用合成的买价
                        "asks": [[synthetic_ask, 1.0]],  # 使用合成的卖价
                        "timestamp": int(time.time() * 1000)
                    }

                # 使用修复后的排序数据
                return {
                    "symbol": symbol,
                    "bids": [[float(b[0]), float(b[1])] for b in sorted_bids[:depth]],
                    "asks": [[float(a[0]), float(a[1])] for a in sorted_asks[:depth]],
                    "timestamp": data.get("lastUpdateId", int(time.time() * 1000))
                }

            return {
                "symbol": symbol,
                "bids": [],
                "asks": [],
                "timestamp": int(time.time() * 1000)
            }

        except Exception as e:
            console.print(f"[red]获取盘口失败: {e}[/red]")
            return {}