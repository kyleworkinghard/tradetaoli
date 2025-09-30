"""
GoodDEX CLI 异常定义
"""

class GoodDEXError(Exception):
    """GoodDEX 基础异常"""
    pass


class APIError(GoodDEXError):
    """API 调用异常"""
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AuthenticationError(GoodDEXError):
    """认证异常"""
    pass


class ConfigurationError(GoodDEXError):
    """配置异常"""
    pass


class ConnectionError(GoodDEXError):
    """连接异常"""
    pass


class ValidationError(GoodDEXError):
    """验证异常"""
    pass


class TradingError(GoodDEXError):
    """交易异常"""
    pass


class AccountError(GoodDEXError):
    """账户异常"""
    pass