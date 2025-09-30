"""
配置管理模块
"""

import os
import toml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from rich.console import Console

console = Console()


@dataclass
class APIConfig:
    """API 配置"""
    base_url: str = "http://localhost:8000"
    timeout: int = 30
    retry_count: int = 3
    verify_ssl: bool = True


@dataclass
class TradingConfig:
    """交易配置"""
    default_leverage: int = 1
    max_position_size: float = 10.0
    risk_limit: float = 0.02
    min_profit_threshold: float = 10.0
    max_spread_threshold: float = 0.5


@dataclass
class DisplayConfig:
    """显示配置"""
    decimal_places: int = 4
    timezone: str = "UTC"
    color_theme: str = "dark"
    table_style: str = "grid"
    date_format: str = "%Y-%m-%d %H:%M:%S"


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "~/.gooddex/logs/gooddex.log"
    max_size: str = "10MB"
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    """主配置类"""
    api: APIConfig = field(default_factory=APIConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_dir = Path.home() / ".gooddex"
        self.config_file = Path(config_file) if config_file else self.config_dir / "config.toml"
        self.config = Config()

        # 确保配置目录存在
        self.config_dir.mkdir(exist_ok=True)
        (self.config_dir / "logs").mkdir(exist_ok=True)

        # 加载配置
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = toml.load(f)

                # 更新配置
                if 'api' in data:
                    for key, value in data['api'].items():
                        if hasattr(self.config.api, key):
                            setattr(self.config.api, key, value)

                if 'trading' in data:
                    for key, value in data['trading'].items():
                        if hasattr(self.config.trading, key):
                            setattr(self.config.trading, key, value)

                if 'display' in data:
                    for key, value in data['display'].items():
                        if hasattr(self.config.display, key):
                            setattr(self.config.display, key, value)

                if 'logging' in data:
                    for key, value in data['logging'].items():
                        if hasattr(self.config.logging, key):
                            setattr(self.config.logging, key, value)

            except Exception as e:
                console.print(f"[yellow]⚠️  加载配置文件失败: {e}[/yellow]")
                console.print("[yellow]使用默认配置[/yellow]")
        else:
            # 创建默认配置文件
            self.save_config()

    def save_config(self) -> None:
        """保存配置到文件"""
        config_data = {
            'api': {
                'base_url': self.config.api.base_url,
                'timeout': self.config.api.timeout,
                'retry_count': self.config.api.retry_count,
                'verify_ssl': self.config.api.verify_ssl,
            },
            'trading': {
                'default_leverage': self.config.trading.default_leverage,
                'max_position_size': self.config.trading.max_position_size,
                'risk_limit': self.config.trading.risk_limit,
                'min_profit_threshold': self.config.trading.min_profit_threshold,
                'max_spread_threshold': self.config.trading.max_spread_threshold,
            },
            'display': {
                'decimal_places': self.config.display.decimal_places,
                'timezone': self.config.display.timezone,
                'color_theme': self.config.display.color_theme,
                'table_style': self.config.display.table_style,
                'date_format': self.config.display.date_format,
            },
            'logging': {
                'level': self.config.logging.level,
                'file': self.config.logging.file,
                'max_size': self.config.logging.max_size,
                'backup_count': self.config.logging.backup_count,
                'format': self.config.logging.format,
            }
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                toml.dump(config_data, f)
        except Exception as e:
            console.print(f"[red]❌ 保存配置文件失败: {e}[/red]")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config

        try:
            for k in keys:
                value = getattr(value, k)
            return value
        except AttributeError:
            return default

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        keys = key.split('.')
        if len(keys) != 2:
            raise ValueError("配置键必须是 'section.key' 格式")

        section, config_key = keys
        section_obj = getattr(self.config, section, None)

        if section_obj is None:
            raise ValueError(f"未知的配置节: {section}")

        if not hasattr(section_obj, config_key):
            raise ValueError(f"未知的配置项: {section}.{config_key}")

        # 类型转换
        current_value = getattr(section_obj, config_key)
        if isinstance(current_value, bool):
            value = str(value).lower() in ('true', '1', 'yes', 'on')
        elif isinstance(current_value, int):
            value = int(value)
        elif isinstance(current_value, float):
            value = float(value)

        setattr(section_obj, config_key, value)
        self.save_config()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config(config_file: Optional[str] = None) -> ConfigManager:
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_file)
    return _config_manager


def init_config(config_file: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_file)
    return _config_manager