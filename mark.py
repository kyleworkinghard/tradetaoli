#!/usr/bin/env python3
"""
价差数据记录脚本 - mark.py
记录Aster和Backpack交易所的BTC、ETH合约盘口价差数据
用于分析套利机会和价差规律
"""

import asyncio
import json
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
import signal
import sys

# 导入项目核心模块
from src.core.exchange_factory import ExchangeFactory
from src.core.config import get_config

class SpreadRecorder:
    """价差数据记录器"""

    def __init__(self):
        self.running = False
        self.factory = None
        self.aster_adapter = None
        self.backpack_adapter = None

        # 配置参数
        self.symbols = ['BTCUSDT', 'ETHUSDT']  # 支持的交易对
        self.record_interval = 1.0  # 记录间隔(秒)
        self.data_dir = Path('spread_data')

        # 数据存储
        self.csv_files = {}
        self.csv_writers = {}

        # 统计计数
        self.record_count = 0
        self.start_time = None

        # 初始化数据目录
        self.data_dir.mkdir(exist_ok=True)

        print("🔍 价差数据记录器初始化完成")

    async def initialize(self):
        """初始化交易所连接"""
        try:
            print("🚀 初始化交易所连接...")

            # 创建交易所工厂
            self.factory = ExchangeFactory()

            # 获取配置文件中的账户ID (假设配置了Aster和Backpack账户)
            accounts = self.factory.load_accounts()

            # 查找Aster和Backpack账户
            aster_account_id = None
            backpack_account_id = None

            for account_id, account_info in accounts.items():
                if account_info['exchange'].lower() == 'aster':
                    aster_account_id = account_id
                elif account_info['exchange'].lower() == 'backpack':
                    backpack_account_id = account_id

            if not aster_account_id or not backpack_account_id:
                raise Exception("请在accounts.json中配置Aster和Backpack账户信息")

            # 创建交易所适配器
            aster_info = self.factory.create_exchange_info(aster_account_id, "BTCUSDT")
            backpack_info = self.factory.create_exchange_info(backpack_account_id, "BTCUSDT")

            self.aster_adapter = aster_info.adapter
            self.backpack_adapter = backpack_info.adapter

            print(f"✅ Aster交易所连接成功")
            print(f"✅ Backpack交易所连接成功")

            # 初始化CSV文件
            self._init_csv_files()

        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            raise

    def _init_csv_files(self):
        """初始化CSV文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for symbol in self.symbols:
            filename = f"spread_{symbol}_{timestamp}.csv"
            filepath = self.data_dir / filename

            # 打开CSV文件
            file_obj = open(filepath, 'w', newline='', encoding='utf-8')
            writer = csv.writer(file_obj)

            # 写入CSV头部
            headers = [
                'timestamp',
                'datetime',
                'symbol',
                'aster_bid',
                'aster_ask',
                'aster_mid',
                'backpack_bid',
                'backpack_ask',
                'backpack_mid',
                'spread_1',  # Aster买入 -> Backpack卖出
                'spread_2',  # Backpack买入 -> Aster卖出
                'best_spread',
                'best_direction'
            ]
            writer.writerow(headers)

            self.csv_files[symbol] = file_obj
            self.csv_writers[symbol] = writer

            print(f"📁 创建数据文件: {filepath}")

    def _convert_symbol(self, symbol: str, exchange: str) -> str:
        """转换交易对格式"""
        if exchange.lower() == 'aster':
            return symbol  # BTCUSDT
        elif exchange.lower() == 'backpack':
            if symbol == 'BTCUSDT':
                return 'BTC_USDC_PERP'
            elif symbol == 'ETHUSDT':
                return 'ETH_USDC_PERP'
        return symbol

    async def get_orderbook(self, adapter, symbol: str, exchange: str) -> Dict:
        """获取盘口数据"""
        try:
            converted_symbol = self._convert_symbol(symbol, exchange)
            orderbook = await adapter.get_orderbook(converted_symbol, 5)
            return orderbook
        except Exception as e:
            print(f"⚠️ 获取{exchange} {symbol}盘口失败: {e}")
            return None

    async def calculate_spread(self, symbol: str) -> Dict:
        """计算价差"""
        try:
            # 并行获取两个交易所的盘口数据
            aster_book, backpack_book = await asyncio.gather(
                self.get_orderbook(self.aster_adapter, symbol, 'aster'),
                self.get_orderbook(self.backpack_adapter, symbol, 'backpack'),
                return_exceptions=True
            )

            if not aster_book or not backpack_book:
                return None

            # 提取价格数据
            aster_bid = float(aster_book["bids"][0][0])
            aster_ask = float(aster_book["asks"][0][0])
            aster_mid = (aster_bid + aster_ask) / 2

            backpack_bid = float(backpack_book["bids"][0][0])
            backpack_ask = float(backpack_book["asks"][0][0])
            backpack_mid = (backpack_bid + backpack_ask) / 2

            # 计算价差
            spread_1 = backpack_bid - aster_ask  # Aster买入 -> Backpack卖出
            spread_2 = aster_bid - backpack_ask  # Backpack买入 -> Aster卖出

            # 确定最佳价差方向
            if abs(spread_1) > abs(spread_2):
                best_spread = spread_1
                best_direction = "Aster买入->Backpack卖出" if spread_1 > 0 else "Aster卖出->Backpack买入"
            else:
                best_spread = spread_2
                best_direction = "Backpack买入->Aster卖出" if spread_2 > 0 else "Backpack卖出->Aster买入"

            return {
                'symbol': symbol,
                'aster_bid': aster_bid,
                'aster_ask': aster_ask,
                'aster_mid': aster_mid,
                'backpack_bid': backpack_bid,
                'backpack_ask': backpack_ask,
                'backpack_mid': backpack_mid,
                'spread_1': spread_1,
                'spread_2': spread_2,
                'best_spread': best_spread,
                'best_direction': best_direction
            }

        except Exception as e:
            print(f"⚠️ 计算{symbol}价差失败: {e}")
            return None

    def record_data(self, spread_data: Dict):
        """记录数据到CSV"""
        try:
            symbol = spread_data['symbol']
            now = datetime.now(timezone.utc)

            row = [
                int(now.timestamp()),
                now.strftime('%Y-%m-%d %H:%M:%S UTC'),
                symbol,
                spread_data['aster_bid'],
                spread_data['aster_ask'],
                spread_data['aster_mid'],
                spread_data['backpack_bid'],
                spread_data['backpack_ask'],
                spread_data['backpack_mid'],
                spread_data['spread_1'],
                spread_data['spread_2'],
                spread_data['best_spread'],
                spread_data['best_direction']
            ]

            self.csv_writers[symbol].writerow(row)
            self.csv_files[symbol].flush()  # 立即写入磁盘

            self.record_count += 1

        except Exception as e:
            print(f"⚠️ 记录数据失败: {e}")

    def print_status(self, spread_data: Dict):
        """打印状态信息"""
        symbol = spread_data['symbol']
        now = datetime.now()
        runtime = (now - self.start_time).total_seconds() if self.start_time else 0

        # 价差颜色显示
        spread_1 = spread_data['spread_1']
        spread_2 = spread_data['spread_2']

        spread_1_color = "🟢" if spread_1 > 0 else "🔴"
        spread_2_color = "🟢" if spread_2 > 0 else "🔴"

        print(f"[{now.strftime('%H:%M:%S')}] {symbol} | "
              f"A买→B卖: {spread_1_color}{spread_1:+.2f} | "
              f"B买→A卖: {spread_2_color}{spread_2:+.2f} | "
              f"最佳: {spread_data['best_spread']:+.2f} | "
              f"记录数: {self.record_count} | "
              f"运行时间: {runtime:.0f}s")

    async def run(self):
        """运行数据记录"""
        self.running = True
        self.start_time = datetime.now()

        print(f"📊 开始记录价差数据...")
        print(f"📊 监控品种: {', '.join(self.symbols)}")
        print(f"📊 记录间隔: {self.record_interval}秒")
        print(f"📊 数据保存: {self.data_dir.absolute()}")
        print(f"📊 按Ctrl+C停止记录\n")

        while self.running:
            try:
                # 并行获取所有交易对的价差数据
                tasks = [self.calculate_spread(symbol) for symbol in self.symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if result and isinstance(result, dict):
                        # 记录数据
                        self.record_data(result)

                        # 打印状态
                        self.print_status(result)

                # 等待下次记录
                await asyncio.sleep(self.record_interval)

            except Exception as e:
                print(f"❌ 记录过程异常: {e}")
                await asyncio.sleep(5)  # 异常后等待5秒继续

    def stop(self):
        """停止记录"""
        self.running = False
        print(f"\n🛑 停止数据记录...")

    async def cleanup(self):
        """清理资源"""
        # 关闭CSV文件
        for file_obj in self.csv_files.values():
            file_obj.close()

        # 清理交易所连接
        if self.factory:
            await self.factory.cleanup_adapters()

        # 打印统计信息
        if self.start_time:
            runtime = (datetime.now() - self.start_time).total_seconds()
            print(f"📊 总记录数: {self.record_count}")
            print(f"📊 运行时间: {runtime:.1f}秒")
            print(f"📊 平均记录频率: {self.record_count/runtime*60:.1f}条/分钟")

        print(f"🧹 资源清理完成")

async def main():
    """主函数"""
    recorder = SpreadRecorder()

    # 信号处理
    def signal_handler(signum, frame):
        print(f"\n接收到信号 {signum}")
        recorder.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 初始化
        await recorder.initialize()

        # 开始记录
        await recorder.run()

    except KeyboardInterrupt:
        print(f"\n用户中断")
    except Exception as e:
        print(f"❌ 程序异常: {e}")
    finally:
        await recorder.cleanup()

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════╗
║        价差数据记录器 - mark.py        ║
║      Aster & Backpack 价差监控        ║
╚═══════════════════════════════════════╝
    """)

    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)