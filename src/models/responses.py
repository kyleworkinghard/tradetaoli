"""
API 响应数据模型
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum


class ExchangeType(str, Enum):
    """交易所类型"""
    ASTER = "aster"
    OKX = "okx"


class TradeStatus(str, Enum):
    """交易状态"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PositionSide(str, Enum):
    """仓位方向"""
    LONG = "long"
    SHORT = "short"


# 认证相关模型
class AuthToken(BaseModel):
    """认证令牌"""
    access_token: str
    token_type: str
    expires_in: int


class UserInfo(BaseModel):
    """用户信息"""
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime


# 账户相关模型
class Account(BaseModel):
    """账户信息"""
    id: int
    name: str
    exchange: ExchangeType
    is_active: bool
    is_testnet: bool
    total_volume: float
    total_trades: int
    total_fees: float
    created_at: datetime


class AccountBalance(BaseModel):
    """账户余额"""
    currency: str
    free_balance: float
    used_balance: float
    total_balance: float


class AccountDetail(BaseModel):
    """账户详情"""
    account: Account
    balances: List[AccountBalance]
    connection_status: str
    last_updated: datetime


# 交易相关模型
class TradingSession(BaseModel):
    """交易会话"""
    id: int
    session_name: str
    symbol: str
    position_size: float
    leverage: int
    hedge_direction: str
    status: TradeStatus
    total_volume: float
    total_fees: float
    total_pnl: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class Trade(BaseModel):
    """交易记录"""
    id: int
    session_id: int
    account_id: int
    order_id: str
    exchange: ExchangeType
    symbol: str
    side: PositionSide
    amount: float
    price: float
    filled_amount: float
    average_price: Optional[float]
    fee: float
    fee_currency: str
    pnl: float
    status: TradeStatus
    order_type: str
    is_open: bool
    created_at: datetime
    filled_at: Optional[datetime]


class Position(BaseModel):
    """持仓信息"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    unrealized_pnl: float


# 统计相关模型
class TradingOverview(BaseModel):
    """交易概览"""
    total_sessions: int
    active_sessions: int
    completed_sessions: int
    failed_sessions: int
    total_volume: float
    total_fees: float
    total_pnl: float
    aster_volume: float
    okx_volume: float
    aster_fees: float
    okx_fees: float


class VolumeStatistics(BaseModel):
    """交易量统计"""
    period: str
    date: datetime
    total_volume: float
    aster_volume: float
    okx_volume: float
    trade_count: int


class FeeStatistics(BaseModel):
    """手续费统计"""
    period: str
    date: datetime
    total_fees: float
    aster_fees: float
    okx_fees: float
    funding_fees: float


class PnLStatistics(BaseModel):
    """盈亏统计"""
    period: str
    date: datetime
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    win_rate: float
    avg_profit_per_trade: float


class AccountPerformance(BaseModel):
    """账户绩效"""
    account_id: int
    account_name: str
    exchange: ExchangeType
    total_volume: float
    total_trades: int
    total_fees: float
    total_pnl: float
    win_rate: float
    avg_profit_per_trade: float