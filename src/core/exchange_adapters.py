"""
交易所适配器 - 真实API连接
"""

import ccxt
import asyncio
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import httpx
from rich.console import Console
from rich import print as rprint

# Backpack相关导入
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import hashes
    BACKPACK_AVAILABLE = True
except ImportError:
    BACKPACK_AVAILABLE = False
    print("⚠️ cryptography not installed. Backpack support disabled. Run: pip install cryptography")

console = Console()


class ExchangeAdapter:
    """交易所适配器基类"""

    def __init__(self, api_key: str, secret: str, passphrase: Optional[str] = None, testnet: bool = False):
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.testnet = testnet
        self.client = None

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        raise NotImplementedError

    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取余额"""
        raise NotImplementedError

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓"""
        raise NotImplementedError


class OKXAdapter(ExchangeAdapter):
    """OKX交易所适配器"""

    def __init__(self, api_key: str, secret: str, passphrase: str, testnet: bool = False):
        super().__init__(api_key, secret, passphrase, testnet)

        # 修改这里：强制使用swap市场（永续合约）
        self.client = ccxt.okx({
            'apiKey': api_key,
            'secret': secret,
            'password': passphrase,
            'sandbox': testnet,
            'options': {
                'defaultType': 'swap'  # 添加这行，强制使用永续合约
            }
        })

    async def test_connection(self) -> Dict[str, Any]:
        """测试OKX连接"""
        try:
            # 获取账户余额来测试连接
            balance = await asyncio.get_event_loop().run_in_executor(
                None, self.client.fetch_balance
            )

            return {
                "success": True,
                "message": "OKX连接测试成功",
                "account_type": "OKX永续合约账户",
                "positions_count": len(balance.get('info', {}))
            }

        except ccxt.AuthenticationError as e:
            return {
                "success": False,
                "message": f"OKX认证失败: {str(e)}"
            }
        except ccxt.NetworkError as e:
            return {
                "success": False,
                "message": f"OKX网络错误: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"OKX连接错误: {str(e)}"
            }

    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取OKX余额"""
        try:
            balance = await asyncio.get_event_loop().run_in_executor(
                None, self.client.fetch_balance
            )

            balances = []
            for currency, amounts in balance.items():
                if currency not in ['info', 'free', 'used', 'total'] and isinstance(amounts, dict) and amounts.get('total', 0) > 0:
                    balances.append({
                        "currency": currency,
                        "free_balance": float(amounts.get('free', 0)),
                        "used_balance": float(amounts.get('used', 0)),
                        "total_balance": float(amounts.get('total', 0))
                    })

            return balances

        except Exception as e:
            console.print(f"[red]获取OKX余额失败: {e}[/red]")
            return []

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取OKX持仓"""
        try:
            positions = await asyncio.get_event_loop().run_in_executor(
                None, self.client.fetch_positions
            )

            active_positions = []
            for pos in positions:
                if float(pos.get('contracts', 0)) != 0:  # 只返回有持仓的
                    active_positions.append({
                        "symbol": pos.get('symbol'),
                        "side": pos.get('side'),
                        "size": float(pos.get('contracts', 0)),
                        "entry_price": float(pos.get('entryPrice', 0)),
                        "mark_price": float(pos.get('markPrice', 0)),
                        "pnl": float(pos.get('unrealizedPnl', 0)),
                        "percentage": float(pos.get('percentage', 0))
                    })

            return active_positions

        except Exception as e:
            console.print(f"[red]获取OKX持仓失败: {e}[/red]")
            return []

    async def get_orderbook(self, symbol: str, depth: int = 5) -> Dict[str, Any]:
        """获取OKX盘口深度"""
        try:
            orderbook = await asyncio.get_event_loop().run_in_executor(
                None, self.client.fetch_order_book, symbol, depth
            )

            return {
                "symbol": symbol,
                "bids": orderbook.get('bids', []),  # 买盘 [[price, size], ...]
                "asks": orderbook.get('asks', []),  # 卖盘 [[price, size], ...]
                "timestamp": orderbook.get('timestamp')
            }

        except Exception as e:
            console.print(f"[red]获取OKX盘口失败: {e}[/red]")
            return {}

    async def place_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = "limit", leverage: int = 1) -> Dict[str, Any]:
        """下单"""
        try:
            # 先设置杠杆
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.set_leverage(leverage, symbol)
            )

            # 确保LIMIT订单有价格
            if order_type == "limit" and price is None:
                raise ValueError("LIMIT订单必须指定价格")

            # OKX永续合约数量转换
            # BTC/USDT:USDT 永续合约，1张 = 0.01 BTC
            # 所以 0.01 BTC = 1张，0.001 BTC = 0.1张
            console.print(f"[yellow]🔍 OKX数量转换调试: 输入数量={amount} BTC[/yellow]")
            
            # 获取合约信息来确定正确的转换方式
            try:
                market = self.client.market(symbol)
                contract_size = market.get('contractSize', 0.01)  # 默认0.01 BTC
                console.print(f"[yellow]🔍 合约规格: 1张 = {contract_size} BTC[/yellow]")
                
                # 计算需要的张数
                contract_amount = amount / contract_size
                console.print(f"[yellow]🔍 计算张数: {amount} BTC ÷ {contract_size} = {contract_amount} 张[/yellow]")
                
            except Exception as e:
                console.print(f"[yellow]⚠️ 无法获取合约信息，使用默认转换: {e}[/yellow]")
                # 默认转换：1张 = 0.01 BTC
                contract_amount = amount / 0.01
                console.print(f"[yellow]🔍 默认转换: {amount} BTC ÷ 0.01 = {contract_amount} 张[/yellow]")

            # OKX永续合约需要指定持仓方向
            pos_side = "long" if side == "buy" else "short"

            # 强制使用LIMIT订单确保Maker成交
            if order_type == "limit":
                console.print(f"[cyan]📋 OKX LIMIT订单 (Maker): {side} {contract_amount} 张 @ {price}[/cyan]")

            # 确保使用永续合约市场
            order = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.create_order(
                    symbol=symbol,
                    type=order_type,  # 确保是"limit"
                    side=side,
                    amount=contract_amount,  # 使用转换后的数量
                    price=price,  # 必须有价格
                    params={
                        'type': 'swap',
                        'posSide': pos_side  # 添加持仓方向参数
                    }
                )
            )

            return {
                "order_id": order.get('id'),
                "symbol": order.get('symbol'),
                "side": order.get('side'),
                "amount": order.get('amount'),
                "price": order.get('price'),
                "status": order.get('status'),
                "timestamp": order.get('timestamp')
            }

        except Exception as e:
            console.print(f"[red]OKX下单失败: {e}[/red]")
            return {}

    async def get_order_status(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
        """获取OKX订单状态"""
        # rprint(f"[yellow]🔍 查询OKX订单状态: {order_id}, symbol: {symbol}[/yellow]")
        try:
            order = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.fetch_order(order_id, symbol)
            )
            # rprint(f"[yellow]📋 OKX订单数据: {order}[/yellow]")
            return {
                "order_id": order.get('id'),
                "status": order.get('status'),
                "filled": order.get('filled'),
                "remaining": order.get('remaining'),
                "amount": order.get('amount')
            }
        except Exception as e:
            rprint(f"[red]获取OKX订单状态失败: {e}[/red]")
            return {"status": "unknown"}

    async def close_position(self, symbol: str, side: str, amount: float, price: float = None, original_pos_side: str = None) -> Dict[str, Any]:
        """OKX专用平仓方法 - 优先使用LIMIT订单(Maker)"""
        try:
            console.print(f"[cyan]📋 OKX平仓: {side} {amount} BTC[/cyan]")

            # 获取合约信息进行数量转换
            try:
                market = self.client.market(symbol)
                contract_size = market.get('contractSize', 0.01)  # 默认0.01 BTC
                contract_amount = amount / contract_size
                console.print(f"[yellow]🔍 平仓数量转换: {amount} BTC ÷ {contract_size} = {contract_amount} 张[/yellow]")
            except Exception as e:
                console.print(f"[yellow]⚠️ 无法获取合约信息，使用默认转换: {e}[/yellow]")
                contract_amount = amount / 0.01

            # 修复：平仓时posSide应该与原开仓方向一致
            if original_pos_side:
                pos_side = original_pos_side  # 使用原始持仓方向
            else:
                # 推断持仓方向（备用）
                pos_side = "long" if side == "sell" else "short"

            console.print(f"[cyan]📋 OKX平仓持仓方向: {pos_side}[/cyan]")

            # 优先使用LIMIT订单平仓
            order_type = "limit" if price else "market"
            console.print(f"[cyan]平仓方式: {order_type.upper()} ({'Maker' if order_type == 'limit' else 'Taker'})[/cyan]")

            create_params = {
                'type': 'swap',
                'reduceOnly': True,
                'posSide': pos_side  # 使用正确的持仓方向
            }

            if order_type == "limit":
                # 确保LIMIT订单有价格
                if price is None:
                    raise ValueError("LIMIT平仓订单必须指定价格")
                
                order = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.create_order(
                        symbol=symbol,
                        type="limit",  # 改为limit
                        side=side,
                        amount=contract_amount,
                        price=price,  # 添加价格参数
                        params=create_params
                    )
                )
            else:
                # 备用市价单
                console.print(f"[yellow]⚠️ 使用市价单平仓 (无价格参数)[/yellow]")
                order = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.create_order(
                        symbol=symbol,
                        type="market",  # 平仓使用市价单确保成交
                        side=side,
                        amount=contract_amount,
                        params=create_params
                    )
                )

            return {
                "order_id": order.get('id'),
                "symbol": order.get('symbol'),
                "side": order.get('side'),
                "amount": order.get('amount'),
                "price": order.get('price'),
                "status": order.get('status'),
                "type": "close_position"
            }

        except Exception as e:
            console.print(f"[red]OKX平仓失败: {e}[/red]")
            return {}

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """撤单"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.client.cancel_order, order_id, symbol
            )
            return True
        except Exception as e:
            console.print(f"[red]OKX撤单失败: {e}[/red]")
            return False

    async def get_fills_history(self, symbol: str = None, order_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取OKX成交历史"""
        try:
            # 使用ccxt的fetch_my_trades方法获取成交历史
            fills = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.fetch_my_trades(
                    symbol=symbol,
                    limit=min(limit, 100),  # OKX限制最大100
                    params={"ordId": order_id} if order_id else {}
                )
            )

            # 转换ccxt格式到统一格式
            result = []
            for fill in fills:
                # 处理时间戳 - ccxt已经返回秒级时间戳
                timestamp = fill.get("timestamp", 0)
                if timestamp and timestamp > 1e12:  # 已经是毫秒
                    timestamp = int(timestamp)
                else:  # 秒级时间戳，转换为毫秒
                    timestamp = int(timestamp * 1000)
                
                result.append({
                    "order_id": fill.get("order"),
                    "symbol": fill.get("symbol"),
                    "side": fill.get("side"),
                    "price": float(fill.get("price", 0)),
                    "quantity": float(fill.get("amount", 0)),
                    "timestamp": timestamp,
                    "fee": float(fill.get("fee", {}).get("cost", 0)),
                    "fee_currency": fill.get("fee", {}).get("currency", "")
                })

            return result

        except Exception as e:
            print(f"❌ OKX获取成交历史异常: {e}")
            return []


class AsterAdapter(ExchangeAdapter):
    """Aster DEX适配器"""

    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        super().__init__(api_key, secret, None, testnet)
        # 使用真实的Aster API URL
        self.base_url = "https://fapi.asterdex.com"
        self.session = None

    async def _init_session(self):
        """初始化HTTP会话"""
        if not self.session:
            self.session = httpx.AsyncClient(timeout=30)

    def _sign_request(self, params: Dict[str, Any] = None) -> str:
        """生成Aster API签名"""
        if params is None:
            params = {}

        # 添加时间戳和接收窗口
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000

        # 构建查询字符串
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items()) if v is not None])

        # 生成HMAC SHA256签名
        signature = hmac.new(
            self.secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return f"{query_string}&signature={signature}"

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GoodDEX-CLI/1.0"
        }

    async def test_connection(self) -> Dict[str, Any]:
        """测试Aster连接"""
        try:
            await self._init_session()

            # 使用真实的Aster API端点获取账户信息
            path = "/fapi/v2/account"
            query_string = self._sign_request()
            headers = self._get_headers()

            response = await self.session.get(
                f"{self.base_url}{path}?{query_string}",
                headers=headers
            )

            if response.status_code == 200:
                account_data = response.json()
                return {
                    "success": True,
                    "message": "Aster DEX连接测试成功",
                    "account_type": "Aster DEX账户",
                    "account_id": account_data.get("accountAlias", f"aster_{self.api_key[:8]}")
                }
            else:
                error_data = None
                try:
                    error_data = response.json()
                except:
                    pass

                error_msg = error_data.get('msg', f"HTTP {response.status_code}") if error_data else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "message": f"Aster API错误: {error_msg}"
                }

        except httpx.ConnectError:
            return {
                "success": False,
                "message": "无法连接到Aster服务器，请检查网络连接"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Aster连接错误: {str(e)}"
            }

    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取Aster余额"""
        try:
            await self._init_session()

            # 使用真实的Aster API端点获取余额
            path = "/fapi/v2/balance"
            query_string = self._sign_request()
            headers = self._get_headers()

            response = await self.session.get(
                f"{self.base_url}{path}?{query_string}",
                headers=headers
            )

            if response.status_code == 200:
                balance_data = response.json()
                balances = []

                # 处理Aster API返回的余额数据格式
                for item in balance_data:
                    if float(item.get("balance", 0)) > 0:
                        balances.append({
                            "currency": item.get("asset"),
                            "free_balance": float(item.get("availableBalance", 0)),
                            "used_balance": float(item.get("balance", 0)) - float(item.get("availableBalance", 0)),
                            "total_balance": float(item.get("balance", 0))
                        })

                return balances
            else:
                error_data = None
                try:
                    error_data = response.json()
                except:
                    pass

                error_msg = error_data.get('msg', f"HTTP {response.status_code}") if error_data else f"HTTP {response.status_code}"
                console.print(f"[red]获取Aster余额失败: {error_msg}[/red]")
                return []

        except Exception as e:
            console.print(f"[red]获取Aster余额失败: {e}[/red]")
            return []

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取Aster持仓"""
        try:
            await self._init_session()

            # 使用真实的Aster API端点获取持仓
            path = "/fapi/v2/positionRisk"
            query_string = self._sign_request()
            headers = self._get_headers()

            response = await self.session.get(
                f"{self.base_url}{path}?{query_string}",
                headers=headers
            )

            if response.status_code == 200:
                positions_data = response.json()
                positions = []

                # 处理Aster API返回的持仓数据格式
                for pos in positions_data:
                    position_amt = float(pos.get("positionAmt", 0))
                    if position_amt != 0:
                        side = "long" if position_amt > 0 else "short"
                        positions.append({
                            "symbol": pos.get("symbol"),
                            "side": side,
                            "size": abs(position_amt),
                            "entry_price": float(pos.get("entryPrice", 0)),
                            "mark_price": float(pos.get("markPrice", 0)),
                            "pnl": float(pos.get("unRealizedProfit", 0)),
                            "percentage": float(pos.get("percentage", 0))
                        })

                return positions
            else:
                error_data = None
                try:
                    error_data = response.json()
                except:
                    pass

                error_msg = error_data.get('msg', f"HTTP {response.status_code}") if error_data else f"HTTP {response.status_code}"
                console.print(f"[red]获取Aster持仓失败: {error_msg}[/red]")
                return []

        except Exception as e:
            console.print(f"[red]获取Aster持仓失败: {e}[/red]")
            return []

    async def get_orderbook(self, symbol: str, depth: int = 5) -> Dict[str, Any]:
        """获取Aster盘口深度"""
        try:
            await self._init_session()

            # 调用Aster的盘口API - 通常盘口数据是公开的，不需要认证
            path = "/fapi/v1/depth"
            # Aster API支持的depth值: 5, 10, 20, 50, 100, 500, 1000
            valid_depths = [5, 10, 20, 50, 100, 500, 1000]
            depth = min(valid_depths, key=lambda x: abs(x - depth))
            params = {"symbol": symbol, "limit": depth}

            # 不使用认证头部，因为盘口数据通常是公开的
            response = await self.session.get(
                f"{self.base_url}{path}",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "symbol": symbol,
                    "bids": [[float(bid[0]), float(bid[1])] for bid in data.get('bids', [])],
                    "asks": [[float(ask[0]), float(ask[1])] for ask in data.get('asks', [])],
                    "timestamp": data.get('E', int(time.time() * 1000))
                }
            else:
                # 尝试其他可能的endpoint
                try:
                    alt_paths = ["/fapi/v2/depth", "/api/v1/depth", "/v1/depth"]
                    for alt_path in alt_paths:
                        alt_response = await self.session.get(
                            f"{self.base_url}{alt_path}",
                            params=params
                        )
                        if alt_response.status_code == 200:
                            data = alt_response.json()
                            return {
                                "symbol": symbol,
                                "bids": [[float(bid[0]), float(bid[1])] for bid in data.get('bids', [])],
                                "asks": [[float(ask[0]), float(ask[1])] for ask in data.get('asks', [])],
                                "timestamp": data.get('E', int(time.time() * 1000))
                            }
                except:
                    pass

                console.print(f"[red]获取Aster盘口失败: {response.status_code}[/red]")
                try:
                    error_text = response.text
                    console.print(f"[red]错误详情: {error_text[:200]}[/red]")
                except:
                    pass
                return {}

        except Exception as e:
            console.print(f"[red]获取Aster盘口失败: {e}[/red]")
            return {}

    async def place_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = "limit", leverage: int = 1) -> Dict[str, Any]:
        """Aster下单"""
        try:
            await self._init_session()

            # 先设置杠杆
            leverage_path = "/fapi/v1/leverage"
            leverage_params = {
                "symbol": symbol,
                "leverage": leverage
            }
            leverage_query = self._sign_request(leverage_params)
            leverage_headers = self._get_headers()

            await self.session.post(
                f"{self.base_url}{leverage_path}",
                data=leverage_query,
                headers=leverage_headers
            )

            # Aster数量处理 - 确保使用正确的数量单位
            console.print(f"[yellow]🔍 Aster数量调试: 输入数量={amount} BTC[/yellow]")
            
            path = "/fapi/v1/order"
            params = {
                "symbol": symbol,
                "side": side.upper(),
                "type": "MARKET" if order_type == "market" else "LIMIT",
                "quantity": amount  # Aster直接使用BTC数量
            }

            if order_type == "limit" and price:
                params["price"] = price
                params["timeInForce"] = "GTC"

            query_string = self._sign_request(params)
            headers = self._get_headers()

            response = await self.session.post(
                f"{self.base_url}{path}",
                data=query_string,
                headers=headers
            )

            if response.status_code == 200:
                order_data = response.json()
                return {
                    "order_id": order_data.get('orderId'),
                    "symbol": order_data.get('symbol'),
                    "side": order_data.get('side'),
                    "amount": float(order_data.get('origQty', 0)),
                    "price": float(order_data.get('price', 0)),
                    "status": order_data.get('status'),
                    "timestamp": order_data.get('transactTime')
                }
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('msg', f"HTTP {response.status_code}")
                console.print(f"[red]Aster下单失败: {error_msg}[/red]")
                return {}

        except Exception as e:
            console.print(f"[red]Aster下单失败: {e}[/red]")
            return {}

    async def get_order_status(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
        """获取Aster订单状态"""
        # rprint(f"[yellow]🔍 查询Aster订单状态: {order_id}[/yellow]")
        try:
            await self._init_session()

            path = "/fapi/v1/order"
            params = {
                "symbol": symbol if symbol else "BTCUSDT",
                "orderId": order_id
            }

            query_string = self._sign_request(params)
            headers = self._get_headers()

            response = await self.session.get(
                f"{self.base_url}{path}?{query_string}",
                headers=headers
            )

            # rprint(f"[yellow]📋 Aster API响应: {response.status_code}[/yellow]")
            if response.status_code == 200:
                order_data = response.json()
                # rprint(f"[yellow]📋 Aster订单数据: {order_data}[/yellow]")
                return {
                    "order_id": order_data.get('orderId'),
                    "status": order_data.get('status'),
                    "filled": float(order_data.get('executedQty', 0)),
                    "remaining": float(order_data.get('origQty', 0)) - float(order_data.get('executedQty', 0)),
                    "amount": float(order_data.get('origQty', 0))
                }
            else:
                rprint(f"[red]Aster API错误: {response.status_code} - {response.text}[/red]")
                return {"status": "unknown"}

        except Exception as e:
            console.print(f"[red]获取Aster订单状态失败: {e}[/red]")
            return {"status": "unknown"}

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Aster撤单"""
        try:
            await self._init_session()

            path = "/fapi/v1/order"
            params = {
                "symbol": symbol,
                "orderId": order_id
            }

            query_string = self._sign_request(params)
            headers = self._get_headers()

            # 修复：使用DELETE方法，不传data参数
            response = await self.session.delete(
                f"{self.base_url}{path}?{query_string}",
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                console.print(f"[green]✅ Aster撤单成功: {order_id}[/green]")
                return True
            else:
                console.print(f"[red]❌ Aster撤单失败: HTTP {response.status_code}[/red]")
                return False

        except Exception as e:
            console.print(f"[red]❌ Aster撤单失败: {e}[/red]")
            return False

    async def get_fills_history(self, symbol: str = None, order_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取Aster成交历史"""
        try:
            await self._init_session()
            
            params = {"limit": limit}
            if symbol:
                params["symbol"] = symbol
            if order_id:
                params["order_id"] = order_id

            # 修改API端点，可能是这些之一：
            # /api/v1/fills
            # /api/v1/account/fills  
            # /api/v1/trades
            response = await self.session.get(
                f"{self.base_url}/api/v1/account/fills",  # 尝试这个端点
                headers=self._get_headers(),  # 确保使用正确的方法名
                params=params
            )

            if response.status_code == 200:
                fills_data = response.json()
                fills = []

                if isinstance(fills_data, list):
                    for fill in fills_data:
                        fills.append({
                            "order_id": fill.get("order_id"),
                            "symbol": fill.get("symbol"),
                            "side": fill.get("side"),
                            "price": float(fill.get("price", 0)),
                            "quantity": float(fill.get("quantity", 0)),
                            "timestamp": fill.get("timestamp"),
                            "fee": float(fill.get("fee", 0)),
                            "fee_currency": fill.get("fee_currency")
                        })

                return fills
            else:
                print(f"❌ Aster获取成交历史失败: HTTP {response.status_code} - 可能API端点不正确")
                return []

        except Exception as e:
            print(f"❌ Aster获取成交历史异常: {e}")
            return []

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.aclose()


if BACKPACK_AVAILABLE:
    class BackpackAdapter(ExchangeAdapter):
        """Backpack交易所适配器 - 完善的签名机制"""

        def __init__(self, api_key: str, secret: str, testnet: bool = False):
            super().__init__(api_key, secret, None, testnet)
            self.base_url = "https://api.backpack.exchange"
            self.session = None

            # 处理Ed25519私钥
            try:
                # Backpack的secret是base64编码的Ed25519私钥
                private_key_bytes = base64.b64decode(secret)

                # 使用cryptography库创建私钥对象
                if len(private_key_bytes) == 32:
                    # 只有32字节的私钥
                    self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                elif len(private_key_bytes) == 64:
                    # 64字节包含私钥+公钥，取前32字节
                    self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes[:32])
                else:
                    raise ValueError(f"Invalid private key length: {len(private_key_bytes)}")

                console.print(f"[green]✅ Ed25519私钥初始化成功[/green]")

            except Exception as e:
                console.print(f"[red]Ed25519私钥初始化失败: {e}[/red]")
                self.private_key = None

        def _sign_request(self, method: str, path: str, params: Dict[str, Any] = None, body: str = None) -> Dict[str, str]:
            """
            生成Backpack API签名
            
            尝试多种签名格式：
            1. <method><path><timestamp><window><body>
            2. <method><path><body><timestamp><window>
            3. <timestamp><method><path><body>
            """
            if not self.private_key:
                raise ValueError("私钥未初始化")

            # 时间戳（毫秒）
            timestamp = int(time.time() * 1000)
            window = "5000"  # 默认5秒窗口

            # 构建签名字符串
            if method.upper() == "GET" or method.upper() == "DELETE":
                # GET和DELETE请求：包含query string
                if params:
                    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
                    full_path = f"{path}?{query_string}"
                else:
                    full_path = path
                # 尝试格式1: <method><path><timestamp><window>
                sign_str = f"{method.upper()}{full_path}{timestamp}{window}"
            else:
                # POST和PUT请求：包含body
                body_str = body if body else ""
                if params and not body:
                    body_str = json.dumps(params, separators=(',', ':'), sort_keys=True)
                # 尝试格式1: <method><path><timestamp><window><body>
                sign_str = f"{method.upper()}{path}{timestamp}{window}{body_str}"

            # 生成Ed25519签名
            signature_bytes = self.private_key.sign(sign_str.encode('utf-8'))
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')


            # 返回请求头
            return {
                "X-API-Key": self.api_key,
                "X-Signature": signature_b64,
                "X-Timestamp": str(timestamp),
                "X-Window": window,
                "Content-Type": "application/json; charset=utf-8"
            }

        def _sign_request_backpack(self, action: str, timestamp: int = None, params: Dict[str, Any] = None) -> Dict[str, str]:
            """
            生成Backpack API签名 - 使用正确的Backpack格式
            签名格式: instruction={action}{params}&timestamp={timestamp}&window={window}
            参考: auto_trade_backpack_exchange-main 的正确实现
            """
            if not self.private_key:
                raise ValueError("私钥未初始化")

            if timestamp is None:
                timestamp = int(time.time() * 1000)
            window = "5000"

            # 构建参数字符串 - 使用URL查询字符串格式，不是JSON格式
            if params:
                # 处理布尔值
                processed_params = params.copy()
                for key, value in processed_params.items():
                    if isinstance(value, bool):
                        processed_params[key] = str(value).lower()  # true/false

                # 构建查询字符串格式: &key1=value1&key2=value2
                param_str = "&" + "&".join(f"{k}={v}" for k, v in sorted(processed_params.items()))
            else:
                param_str = ""

            # 构建签名字符串: instruction={action}{params}&timestamp={timestamp}&window={window}
            sign_str = f"instruction={action}{param_str}&timestamp={timestamp}&window={window}"

            # 注释掉调试信息
            # console.print(f"[dim]🔐 Backpack签名字符串: {sign_str}[/dim]")

            # 生成签名
            signature_bytes = self.private_key.sign(sign_str.encode('utf-8'))
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

            return {
                "X-API-Key": self.api_key,
                "X-Signature": signature_b64,
                "X-Timestamp": str(timestamp),
                "X-Window": window,
                "Content-Type": "application/json; charset=utf-8"
            }

        async def _init_session(self):
            """初始化HTTP会话"""
            if not self.session:
                self.session = httpx.AsyncClient(
                    timeout=30,
                    headers={
                        "User-Agent": "GoodDEX/1.0",
                        "Content-Type": "application/json"
                    }
                )

        async def test_connection(self) -> Dict[str, Any]:
            """测试连接"""
            try:
                await self._init_session()

                # 测试公开端点
                response = await self.session.get(f"{self.base_url}/api/v1/time")

                if response.status_code == 200:
                    # 测试认证端点
                    path = "/api/v1/capital"
                    headers = self._sign_request("GET", path)

                    auth_response = await self.session.get(
                        f"{self.base_url}{path}",
                        headers=headers
                    )

                    if auth_response.status_code == 200:
                        return {"success": True, "message": "Backpack连接成功（认证通过）"}
                    else:
                        return {"success": True, "message": f"Backpack连接成功（认证失败: {auth_response.status_code}）"}
                else:
                    return {"success": False, "message": f"Backpack连接失败: HTTP {response.status_code}"}

            except Exception as e:
                return {"success": False, "message": f"Backpack连接错误: {str(e)}"}

        async def get_balance(self) -> List[Dict[str, Any]]:
            """获取Backpack余额"""
            try:
                await self._init_session()

                path = "/api/v1/capital"
                headers = self._sign_request("GET", path)

                response = await self.session.get(
                    f"{self.base_url}{path}",
                    headers=headers
                )

                console.print(f"[yellow]余额API响应: {response.status_code}[/yellow]")

                if response.status_code == 200:
                    balance_data = response.json()
                    balances = []

                    if isinstance(balance_data, list):
                        for item in balance_data:
                            available = float(item.get("available", 0))
                            locked = float(item.get("locked", 0))
                            if available > 0 or locked > 0:
                                balances.append({
                                    "currency": item.get("symbol", ""),
                                    "free_balance": available,
                                    "used_balance": locked,
                                    "total_balance": available + locked
                                })
                    elif isinstance(balance_data, dict):
                        # 处理字典格式的响应
                        for symbol, data in balance_data.items():
                            if isinstance(data, dict):
                                available = float(data.get("available", 0))
                                locked = float(data.get("locked", 0))
                                if available > 0 or locked > 0:
                                    balances.append({
                                        "currency": symbol,
                                        "free_balance": available,
                                        "used_balance": locked,
                                        "total_balance": available + locked
                                    })

                    return balances
                else:
                    error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
                    console.print(f"[red]获取Backpack余额失败: {error_msg}[/red]")
                    return []

            except Exception as e:
                console.print(f"[red]获取Backpack余额失败: {e}[/red]")
                return []

        async def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
            """获取Backpack盘口深度（公开接口，不需要签名）"""
            try:
                await self._init_session()

                # Backpack使用不同的端点获取盘口
                path = f"/api/v1/depth"
                params = {"symbol": symbol, "limit": min(depth, 100)}

                response = await self.session.get(
                    f"{self.base_url}{path}",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()

                    # 处理Backpack的盘口数据格式
                    raw_bids = data.get('bids', [])
                    raw_asks = data.get('asks', [])

                    # 确保格式为 [[price, size], ...]
                    formatted_bids = []
                    formatted_asks = []

                    for bid in raw_bids:
                        if isinstance(bid, list) and len(bid) >= 2:
                            formatted_bids.append([float(bid[0]), float(bid[1])])
                        elif isinstance(bid, dict):
                            price = float(bid.get('price', 0))
                            size = float(bid.get('size', 0))
                            formatted_bids.append([price, size])

                    for ask in raw_asks:
                        if isinstance(ask, list) and len(ask) >= 2:
                            formatted_asks.append([float(ask[0]), float(ask[1])])
                        elif isinstance(ask, dict):
                            price = float(ask.get('price', 0))
                            size = float(ask.get('size', 0))
                            formatted_asks.append([price, size])

                    # 🔧 修复Backpack的bids排序问题
                    # Backpack返回的bids不是按价格降序排列，需要手动排序
                    if formatted_bids:
                        formatted_bids = sorted(formatted_bids, key=lambda x: x[0], reverse=True)[:depth]
                    if formatted_asks:
                        formatted_asks = sorted(formatted_asks, key=lambda x: x[0])[:depth]

                    # 检查盘口数据质量
                    if formatted_bids and formatted_asks:
                        best_bid = formatted_bids[0][0]
                        best_ask = formatted_asks[0][0]
                        spread = best_ask - best_bid
                        spread_pct = abs(spread) / best_ask * 100

                        console.print(f"[dim]Backpack盘口修复: 买价${best_bid:,.2f}, 卖价${best_ask:,.2f}, 价差${spread:+.2f}[/dim]")

                        # 如果价差仍然异常(>1%)，使用ticker价格
                        if spread_pct > 1.0 or spread < -100:
                            console.print(f"[yellow]⚠️ Backpack盘口仍异常(价差{spread:+.2f})，使用ticker价格[/yellow]")
                        else:
                            spread_pct = (best_ask - best_bid) / best_ask * 100

                        # 如果价差超过5%，说明数据异常，使用ticker价格
                        if spread_pct > 5.0:
                            console.print(f"[yellow]⚠️ Backpack盘口异常(价差{spread_pct:.1f}%)，使用ticker价格[/yellow]")

                            # 获取ticker价格
                            ticker_response = await self.session.get(
                                f"{self.base_url}/api/v1/ticker",
                                params={"symbol": symbol}
                            )

                            if ticker_response.status_code == 200:
                                ticker_data = ticker_response.json()
                                last_price = float(ticker_data.get('lastPrice', best_ask))

                                # 生成合理的盘口价格（围绕lastPrice的小价差）
                                tick_size = 0.1  # BTC_USDC_PERP的tickSize
                                synthetic_bid = round(last_price - tick_size, 1)
                                synthetic_ask = round(last_price + tick_size, 1)

                                return {
                                    "symbol": symbol,
                                    "bids": [[synthetic_bid, 1.0]],
                                    "asks": [[synthetic_ask, 1.0]],
                                    "timestamp": int(time.time() * 1000)
                                }

                    return {
                        "symbol": symbol,
                        "bids": formatted_bids,
                        "asks": formatted_asks,
                        "timestamp": data.get('timestamp', int(time.time() * 1000))
                    }
                else:
                    console.print(f"[red]获取Backpack盘口失败: {response.status_code}[/red]")
                    return {}

            except Exception as e:
                console.print(f"[red]获取Backpack盘口失败: {e}[/red]")
                return {}

        async def _adjust_price_for_backpack(self, symbol: str, price: float, side: str) -> float:
            """调整价格以符合Backpack的价格验证规则"""
            try:
                # 获取ticker价格作为参考
                ticker_response = await self.session.get(
                    f"{self.base_url}/api/v1/ticker",
                    params={"symbol": symbol}
                )

                if ticker_response.status_code == 200:
                    ticker_data = ticker_response.json()
                    last_price = float(ticker_data.get('lastPrice', price))

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

                    console.print(f"[dim]Backpack价格调整: {price} -> {adjusted_price} (参考价:{last_price})[/dim]")
                    return adjusted_price

            except Exception as e:
                console.print(f"[yellow]价格调整失败，使用原价格: {e}[/yellow]")

            return round(price, 1) if price else 0.0

        async def place_order(self, symbol: str, side: str, amount: float, price: float = None,
                              order_type: str = "limit", leverage: int = 1) -> Dict[str, Any]:
            """Backpack下单"""
            try:
                await self._init_session()

                path = "/api/v1/order"

                # 构建订单参数 - 使用Backpack正确的格式
                order_params = {
                    "symbol": symbol,
                    "side": "Bid" if side.lower() == "buy" else "Ask",  # Backpack格式
                    "orderType": "Limit" if order_type.lower() == "limit" else "Market",  # Backpack格式
                    "quantity": str(amount)
                }

                if order_type.lower() == "limit" and price:
                    # 对于限价单，使用Backpack价格验证规则调整价格
                    adjusted_price = await self._adjust_price_for_backpack(symbol, price, side)
                    order_params["price"] = str(adjusted_price)
                    order_params["timeInForce"] = "GTC"  # Backpack需要此参数

                # 如果需要设置杠杆
                if leverage > 1:
                    order_params["leverage"] = leverage

                # 生成请求体
                body = json.dumps(order_params, separators=(',', ':'), sort_keys=True)

                # 生成签名
                headers = self._sign_request("POST", path, body=body)
                headers["Content-Type"] = "application/json"

                # 发送请求
                response = await self.session.post(
                    f"{self.base_url}{path}",
                    content=body,
                    headers=headers
                )

                console.print(f"[yellow]下单响应: {response.status_code}[/yellow]")

                if response.status_code == 200 or response.status_code == 201:
                    order_data = response.json()
                    return {
                        "order_id": order_data.get("id", order_data.get("orderId")),
                        "symbol": order_data.get("symbol"),
                        "side": order_data.get("side"),
                        "amount": float(order_data.get("quantity", 0)),
                        "price": float(order_data.get("price", 0)) if order_data.get("price") else None,
                        "status": order_data.get("status", "new"),
                        "type": "backpack_order"
                    }
                else:
                    error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
                    console.print(f"[red]Backpack下单失败: {error_msg}[/red]")
                    return {}

            except Exception as e:
                console.print(f"[red]Backpack下单失败: {e}[/red]")
                return {}

        async def get_positions(self) -> List[Dict[str, Any]]:
            """获取Backpack持仓"""
            try:
                await self._init_session()

                path = "/api/v1/positions"
                headers = self._sign_request("GET", path)

                response = await self.session.get(f"{self.base_url}{path}", headers=headers)

                if response.status_code == 200:
                    position_data = response.json()
                    positions = []

                    for pos in position_data:
                        position_size = float(pos.get("size", 0))
                        if abs(position_size) > 0:
                            positions.append({
                                "symbol": pos.get("symbol"),
                                "side": "long" if position_size > 0 else "short",
                                "size": abs(position_size),
                                "entry_price": float(pos.get("entryPrice", 0)),
                                "mark_price": float(pos.get("markPrice", 0)),
                                "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                                "percentage": float(pos.get("percentage", 0))
                            })

                    return positions
                else:
                    console.print(f"[red]获取Backpack持仓失败: HTTP {response.status_code}[/red]")
                    return []

            except Exception as e:
                console.print(f"[red]获取Backpack持仓失败: {e}[/red]")
                return []

        async def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
            """获取Backpack盘口深度"""
            try:
                await self._init_session()

                path = "/api/v1/depth"
                params = {"symbol": symbol}
                headers = self._sign_request("GET", path, params)

                response = await self.session.get(f"{self.base_url}{path}", params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()

                    # 🔧 修复Backpack的bids排序问题 - 应用到第二个get_orderbook方法
                    # Backpack返回的bids不是按价格降序排列，需要手动排序
                    raw_bids = data.get('bids', [])
                    raw_asks = data.get('asks', [])

                    formatted_bids = [[float(bid[0]), float(bid[1])] for bid in raw_bids]
                    formatted_asks = [[float(ask[0]), float(ask[1])] for ask in raw_asks]

                    # 排序修复
                    if formatted_bids:
                        formatted_bids = sorted(formatted_bids, key=lambda x: x[0], reverse=True)[:depth]
                    if formatted_asks:
                        formatted_asks = sorted(formatted_asks, key=lambda x: x[0])[:depth]

                    # 调试输出
                    if formatted_bids and formatted_asks:
                        best_bid = formatted_bids[0][0]
                        best_ask = formatted_asks[0][0]
                        spread = best_ask - best_bid
                        # 注释掉频繁的盘口修复日志
        # console.print(f"[dim]Backpack盘口修复(私有API): 买价${best_bid:,.2f}, 卖价${best_ask:,.2f}, 价差${spread:+.2f}[/dim]")

                    return {
                        "symbol": symbol,
                        "bids": formatted_bids,
                        "asks": formatted_asks,
                        "timestamp": data.get('lastUpdateId', int(time.time() * 1000))
                    }
                else:
                    console.print(f"[red]获取Backpack盘口失败: {response.status_code}[/red]")
                    return {}

            except Exception as e:
                console.print(f"[red]获取Backpack盘口失败: {e}[/red]")
                return {}

        async def place_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = "limit", leverage: int = 1) -> Dict[str, Any]:
            """Backpack下单"""
            try:
                await self._init_session()

                # 先设置杠杆
                await self._set_leverage(symbol, leverage)

                path = "/api/v1/order"
                params = {
                    "symbol": symbol,
                    "side": "Bid" if side.lower() == "buy" else "Ask",
                    "orderType": "Limit" if order_type.lower() == "limit" else "Market",
                    "quantity": str(amount)
                }

                if order_type.lower() == "limit" and price:
                    params["price"] = str(price)
                    # 添加timeInForce参数，auto_trade版本建议的做法
                    params["timeInForce"] = "GTC"  # Good Till Cancelled

                timestamp = int(time.time() * 1000)
                headers = self._sign_request_backpack("orderExecute", timestamp, params)

                # 使用data而不是json发送，参考auto_trade版本
                import json
                response = await self.session.post(
                    f"{self.base_url}{path}",
                    data=json.dumps(params),
                    headers=headers
                )

                if response.status_code == 200:
                    order_data = response.json()
                    return {
                        "order_id": order_data.get("id", order_data.get("orderId")),
                        "symbol": order_data.get("symbol"),
                        "side": order_data.get("side"),
                        "amount": float(order_data.get("quantity", 0)),
                        "price": float(order_data.get("price", 0)),
                        "status": order_data.get("status", "new"),
                        "type": "backpack_order"
                    }
                elif 200 <= response.status_code < 300:
                    # 处理204等成功状态码
                    return {"status": "success", "message": "Order placed successfully"}
                else:
                    # 改进的错误处理，参考auto_trade版本
                    try:
                        error_data = response.json()
                        error_msg = f"API Error: {error_data.get('code')} - {error_data.get('message')}"
                    except:
                        error_msg = f"HTTP Error {response.status_code}: {response.text}"

                    console.print(f"[red]Backpack下单失败: {error_msg}[/red]")
                    console.print(f"[yellow]请求参数: {params}[/yellow]")
                    return {}

            except Exception as e:
                console.print(f"[red]Backpack下单失败: {e}[/red]")
                return {}

        async def _set_leverage(self, symbol: str, leverage: int):
            """设置杠杆"""
            try:
                path = "/api/v1/leverage"
                params = {
                    "symbol": symbol,
                    "leverage": leverage
                }
                timestamp = int(time.time() * 1000)
                headers = self._sign_request_backpack("leverageSet", timestamp, params)

                # 使用data而不是json发送，保持一致性
                import json
                await self.session.post(
                    f"{self.base_url}{path}",
                    data=json.dumps(params),
                    headers=headers
                )
            except Exception as e:
                console.print(f"[yellow]设置Backpack杠杆失败: {e}[/yellow]")

        async def cancel_order(self, order_id: str, symbol: str = None) -> bool:
            """撤单"""
            try:
                await self._init_session()

                # 使用正确的Backpack撤单API
                path = "/api/v1/order"
                params = {
                    "orderId": str(order_id)
                }
                if symbol:
                    params["symbol"] = symbol

                # 打印调试信息
                console.print(f"[dim]🔍 Backpack撤单请求 - OrderID: {order_id}, Symbol: {symbol}[/dim]")
                console.print(f"[dim]📦 请求参数: {params}[/dim]")

                # 使用Backpack专用签名，action为orderCancel
                timestamp = int(time.time() * 1000)
                headers = self._sign_request_backpack("orderCancel", timestamp, params)

                # 打印headers调试
                console.print(f"[dim]📋 请求头: X-Signature={headers.get('X-API-Signature', 'N/A')[:20]}...[/dim]")

                # DELETE请求
                # 重要：Backpack的DELETE请求需要将参数放在body中
                url = f"{self.base_url}{path}"
                console.print(f"[dim]🌐 请求URL: {url}[/dim]")

                # 将参数转换为JSON字符串
                import json
                json_data = json.dumps(params)
                console.print(f"[dim]📝 请求Body: {json_data}[/dim]")

                # 添加Content-Type header
                headers['Content-Type'] = 'application/json'

                # httpx的DELETE方法使用json参数传递JSON数据
                response = await self.session.request(
                    method="DELETE",
                    url=url,
                    headers=headers,
                    json=params  # 直接传递字典，httpx会自动序列化为JSON
                )

                console.print(f"[dim]📡 响应状态: {response.status_code}[/dim]")

                if response.status_code == 200:
                    result = response.json()
                    console.print(f"[green]✅ Backpack撤单成功: {order_id}[/green]")
                    console.print(f"[dim]响应数据: {result}[/dim]")
                    return True
                elif response.status_code == 404:
                    # 订单可能已经成交或不存在
                    # console.print(f"[yellow]⚠️ Backpack订单不存在或已成交: {order_id}[/yellow]")  # 减少日志噪音
                    return False
                elif response.status_code == 400:
                    # 请求参数错误
                    console.print(f"[red]❌ Backpack撤单失败: HTTP 400 - 请求参数错误[/red]")
                    try:
                        error_detail = response.json()
                        console.print(f"[red]错误详情: {error_detail}[/red]")
                        # 如果是订单已成交的错误，返回False而不是报错
                        if "already filled" in str(error_detail).lower() or "already executed" in str(error_detail).lower():
                            console.print(f"[yellow]订单已成交，无需撤单[/yellow]")
                            return False
                    except:
                        console.print(f"[red]响应内容: {response.text}[/red]")
                    return False
                else:
                    console.print(f"[red]❌ Backpack撤单失败: HTTP {response.status_code}[/red]")
                    try:
                        error_detail = response.json()
                        console.print(f"[red]错误详情: {error_detail}[/red]")
                    except:
                        console.print(f"[red]响应内容: {response.text}[/red]")
                    return False

            except Exception as e:
                console.print(f"[red]❌ Backpack撤单异常: {e}[/red]")
                import traceback
                console.print(f"[red]异常详情: {traceback.format_exc()}[/red]")
                return False

        async def get_order_status(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
            """获取订单状态"""
            try:
                await self._init_session()

                # 使用订单查询API
                path = "/api/v1/order"
                params = {
                    "orderId": str(order_id)
                }
                if symbol:
                    params["symbol"] = symbol

                # 使用Backpack专用签名
                timestamp = int(time.time() * 1000)
                headers = self._sign_request_backpack("orderQuery", timestamp, params)

                response = await self.session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers=headers
                )

                if response.status_code == 200:
                    order_data = response.json()

                    # 处理可能的多种返回格式
                    if isinstance(order_data, dict):
                        # 将Backpack状态映射为通用状态
                        status = order_data.get("status", "").lower()
                        if status in ["new", "open", "partiallyFilled"]:
                            status = "open"
                        elif status in ["filled", "executed"]:
                            status = "filled"
                        elif status == "cancelled":
                            status = "cancelled"

                        return {
                            "order_id": order_data.get("id") or order_data.get("orderId"),
                            "status": status,
                            "filled": float(order_data.get("executedQuantity", 0)),
                            "amount": float(order_data.get("quantity", 0)),
                            "remaining": float(order_data.get("quantity", 0)) - float(order_data.get("executedQuantity", 0))
                        }
                    else:
                        # 如果返回的不是字典，记录原始响应
                        print(f"⚠️ Backpack订单查询返回非预期格式: {order_data}")
                        return {"status": "error", "message": "Invalid response format"}
                elif response.status_code == 404:
                    # 404可能意味着订单已成交或已撤销
                    # print(f"⚠️ Backpack订单不存在(可能已成交): {order_id}")  # 减少日志噪音
                    # 返回可能已成交的状态，让调用方决定如何处理
                    return {
                        "order_id": order_id,
                        "status": "filled",  # 假设为已成交
                        "filled": 0,
                        "amount": 0,
                        "remaining": 0,
                        "message": "Order not found - possibly filled"
                    }
                else:
                    print(f"❌ Backpack订单查询失败: HTTP {response.status_code}")
                    return {"status": "error", "message": f"HTTP {response.status_code}"}

            except Exception as e:
                print(f"❌ Backpack获取订单状态异常: {e}")
                return {"status": "error", "message": str(e)}

        async def close_position(self, symbol: str, side: str, amount: float, price: float = None, original_pos_side: str = None) -> Dict[str, Any]:
            """Backpack平仓方法"""
            try:
                console.print(f"[cyan]📋 Backpack平仓: {side} {amount} BTC[/cyan]")

                # 反向平仓
                close_side = "sell" if side == "buy" else "buy"
                
                return await self.place_order(symbol, close_side, amount, price, "limit" if price else "market", 1)

            except Exception as e:
                console.print(f"[red]Backpack平仓失败: {e}[/red]")
                return {}

        async def get_fills_history(self, symbol: str = None, order_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
            """获取Backpack成交历史"""
            try:
                await self._init_session()
                
                params = {"limit": limit}
                if symbol:
                    params["symbol"] = symbol
                if order_id:
                    params["orderId"] = order_id

                # 修复：只传递action和timestamp，不传递params
                response = await self.session.get(
                    f"{self.base_url}wapi/v1/history/fills",
                    headers=self._sign_request_backpack("fillHistoryQueryAll", int(time.time() * 1000), params),
                    params=params  # params通过URL参数传递，不是headers
                )

                if response.status_code == 200:
                    fills_data = response.json()
                    fills = []

                    for fill in fills_data:
                        fills.append({
                            "order_id": fill.get("orderId"),
                            "symbol": fill.get("symbol"),
                            "side": fill.get("side"),
                            "price": float(fill.get("price", 0)),
                            "quantity": float(fill.get("quantity", 0)),
                            "timestamp": fill.get("timestamp"),
                            "fee": float(fill.get("feeAmount", 0)),
                            "fee_currency": fill.get("feeCurrency")
                        })

                    return fills
                else:
                    print(f"❌ Backpack获取成交历史失败: HTTP {response.status_code}")
                    return []

            except Exception as e:
                print(f"❌ Backpack获取成交历史异常: {e}")
                return []

        async def get_trade_history_for_stats(self, symbol: str = None, limit: int = 20) -> List[Dict[str, Any]]:
            """专门用于统计的成交历史获取方法 - 不影响交易功能"""
            try:
                await self._init_session()
                
                params = {"limit": limit}
                if symbol:
                    params["symbol"] = symbol

                # 尝试不同的端点，但不影响交易API
                endpoints = [
                    "api/v1/account/trades",
                    "api/v1/trades",
                    "api/v1/account/fills"
                ]

                for endpoint in endpoints:
                    try:
                        response = await self.session.get(
                            f"{self.base_url}{endpoint}",
                            headers=self._get_headers(),
                            params=params
                        )

                        if response.status_code == 200:
                            fills_data = response.json()
                            print(f"✅ Aster统计API端点成功: {endpoint}")

                            fills = []
                            if isinstance(fills_data, list):
                                for fill in fills_data:
                                    fills.append({
                                        "order_id": fill.get("order_id"),
                                        "symbol": fill.get("symbol"),
                                        "side": fill.get("side"),
                                        "price": float(fill.get("price", 0)),
                                        "quantity": float(fill.get("quantity", 0)),
                                        "timestamp": fill.get("timestamp"),
                                        "fee": float(fill.get("fee", 0)),
                                        "fee_currency": fill.get("fee_currency")
                                    })
                            return fills

                    except Exception as e:
                        continue

                return []  # 失败时返回空列表，不影响交易功能

            except Exception as e:
                print(f"❌ Aster统计功能异常: {e}")
                return []

        async def get_trade_history_for_stats(self, symbol: str = None, limit: int = 20) -> List[Dict[str, Any]]:
            """专门用于统计的成交历史获取方法 - 不影响交易功能"""
            try:
                await self._init_session()
                
                # 创建一个独立的简单请求，不依赖复杂的签名逻辑
                params = {"limit": limit}
                if symbol:
                    params["symbol"] = symbol

                # 使用最简单的方式，避免影响交易签名
                timestamp = int(time.time() * 1000)
                simple_headers = {
                    'X-API-Key': self.api_key,
                    'X-Timestamp': str(timestamp),
                    'Content-Type': 'application/json'
                }

                # 尝试不带签名的公开端点（如果有）
                try:
                    response = await self.session.get(
                        f"{self.base_url}wapi/v1/history/fills",
                        headers=simple_headers,
                        params=params
                    )

                    if response.status_code == 200:
                        fills_data = response.json()
                        print(f"✅ Backpack统计获取到 {len(fills_data)} 条记录")

                        fills = []
                        for fill in fills_data:
                            fills.append({
                                "order_id": fill.get("orderId"),
                                "symbol": fill.get("symbol"),
                                "side": fill.get("side"),
                                "price": float(fill.get("price", 0)),
                                "quantity": float(fill.get("quantity", 0)),
                                "timestamp": fill.get("timestamp"),
                                "fee": float(fill.get("feeAmount", 0)),
                                "fee_currency": fill.get("feeCurrency")
                            })
                        return fills

                except Exception as e:
                    print(f"⚠️ Backpack统计端点访问失败: {e}")

                return []  # 失败时返回空列表，不影响交易功能

            except Exception as e:
                print(f"❌ Backpack统计功能异常: {e}")
                return []

        async def close(self):
            """关闭会话"""
            if self.session:
                await self.session.aclose()
else:
    # 如果cryptography不可用，创建一个占位符类
    class BackpackAdapter:
        def __init__(self, *args, **kwargs):
            raise ImportError("cryptography not installed. Run: pip install cryptography")


def get_exchange_adapter(exchange: str, api_key: str, secret: str,
                        passphrase: Optional[str] = None, testnet: bool = False) -> ExchangeAdapter:
    """获取交易所适配器"""
    if exchange.lower() == "okx":
        if not passphrase:
            raise ValueError("OKX需要passphrase")
        return OKXAdapter(api_key, secret, passphrase, testnet)
    elif exchange.lower() == "aster":
        return AsterAdapter(api_key, secret, testnet)
    elif exchange.lower() == "backpack":
        if not BACKPACK_AVAILABLE:
            raise ImportError("cryptography not installed. Run: pip install cryptography")
        return BackpackAdapter(api_key, secret, testnet)
    else:
        raise ValueError(f"不支持的交易所: {exchange}")