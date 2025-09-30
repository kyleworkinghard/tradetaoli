#!/usr/bin/env python3
"""
价差数据分析脚本 - analyze.py
分析mark.py记录的价差数据，发现套利机会和规律
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import argparse
import glob
from datetime import datetime
import sys

class SpreadAnalyzer:
    """价差数据分析器"""

    def __init__(self, data_dir: str = "spread_data"):
        self.data_dir = Path(data_dir)
        self.data = {}

        # 设置中文字体和样式
        plt.rcParams['font.sans-serif'] = ['Arial', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False
        sns.set_style("whitegrid")

        print("📊 价差数据分析器初始化完成")

    def load_data(self, symbol: str = None, days: int = None):
        """加载数据文件"""
        try:
            print(f"📂 从 {self.data_dir} 加载数据...")

            # 查找CSV文件
            if symbol:
                pattern = f"spread_{symbol}_*.csv"
            else:
                pattern = "spread_*.csv"

            csv_files = list(self.data_dir.glob(pattern))

            if not csv_files:
                print(f"❌ 未找到匹配的数据文件: {pattern}")
                return False

            print(f"📁 发现 {len(csv_files)} 个数据文件")

            # 加载所有CSV文件
            all_data = []
            for file in csv_files:
                print(f"📖 读取: {file.name}")
                df = pd.read_csv(file)
                df['datetime'] = pd.to_datetime(df['datetime'])
                all_data.append(df)

            # 合并数据
            if all_data:
                combined_data = pd.concat(all_data, ignore_index=True)
                combined_data = combined_data.sort_values('datetime')

                # 按天数过滤
                if days:
                    cutoff_date = combined_data['datetime'].max() - pd.Timedelta(days=days)
                    combined_data = combined_data[combined_data['datetime'] >= cutoff_date]

                # 按交易对分组
                for sym in combined_data['symbol'].unique():
                    self.data[sym] = combined_data[combined_data['symbol'] == sym].copy()

                total_records = sum(len(df) for df in self.data.values())
                print(f"✅ 加载完成: {total_records} 条记录")
                print(f"📊 交易对: {list(self.data.keys())}")

                return True

        except Exception as e:
            print(f"❌ 加载数据失败: {e}")
            return False

    def basic_statistics(self):
        """基础统计分析"""
        print("\n" + "="*50)
        print("📊 基础统计分析")
        print("="*50)

        for symbol, df in self.data.items():
            print(f"\n🔸 {symbol} 统计信息:")
            print(f"   记录条数: {len(df):,}")
            print(f"   时间范围: {df['datetime'].min()} ~ {df['datetime'].max()}")

            # 价差统计
            spread_cols = ['spread_1', 'spread_2', 'best_spread']
            spread_stats = df[spread_cols].describe()

            print(f"\n   价差统计:")
            print(f"   方向1 (A买→B卖): 均值{spread_stats.loc['mean', 'spread_1']:.2f}, "
                  f"标准差{spread_stats.loc['std', 'spread_1']:.2f}")
            print(f"   方向2 (B买→A卖): 均值{spread_stats.loc['mean', 'spread_2']:.2f}, "
                  f"标准差{spread_stats.loc['std', 'spread_2']:.2f}")
            print(f"   最佳价差: 均值{spread_stats.loc['mean', 'best_spread']:.2f}, "
                  f"标准差{spread_stats.loc['std', 'best_spread']:.2f}")

            # 套利机会统计
            profitable_1 = (df['spread_1'] > 1.0).sum()
            profitable_2 = (df['spread_2'] > 1.0).sum()
            total_profitable = profitable_1 + profitable_2

            print(f"\n   套利机会 (价差>1美元):")
            print(f"   A买→B卖: {profitable_1} 次 ({profitable_1/len(df)*100:.1f}%)")
            print(f"   B买→A卖: {profitable_2} 次 ({profitable_2/len(df)*100:.1f}%)")
            print(f"   总计: {total_profitable} 次 ({total_profitable/len(df)*100:.1f}%)")

    def spread_distribution(self):
        """价差分布分析"""
        print("\n" + "="*50)
        print("📈 价差分布分析")
        print("="*50)

        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Spread Distribution Analysis', fontsize=16)

        for i, (symbol, df) in enumerate(self.data.items()):
            row = i // 2
            col = i % 2

            if row < 2 and col < 2:
                ax = axes[row, col]

                # 绘制价差分布直方图
                ax.hist(df['spread_1'], bins=50, alpha=0.7, label='A买→B卖', color='blue')
                ax.hist(df['spread_2'], bins=50, alpha=0.7, label='B买→A卖', color='red')
                ax.axvline(x=1.0, color='green', linestyle='--', label='盈利线(+1)')
                ax.axvline(x=-1.0, color='green', linestyle='--')
                ax.set_title(f'{symbol} Spread Distribution')
                ax.set_xlabel('Spread (USD)')
                ax.set_ylabel('Frequency')
                ax.legend()
                ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.data_dir / 'spread_distribution.png', dpi=300, bbox_inches='tight')
        print(f"💾 价差分布图保存: {self.data_dir / 'spread_distribution.png'}")

    def time_series_analysis(self):
        """时间序列分析"""
        print("\n" + "="*50)
        print("⏰ 时间序列分析")
        print("="*50)

        fig, axes = plt.subplots(len(self.data), 1, figsize=(15, 6*len(self.data)))
        if len(self.data) == 1:
            axes = [axes]

        for i, (symbol, df) in enumerate(self.data.items()):
            ax = axes[i]

            # 重采样为分钟数据
            df_resampled = df.set_index('datetime').resample('1T').mean()

            ax.plot(df_resampled.index, df_resampled['spread_1'],
                   label='A买→B卖', alpha=0.8, linewidth=1)
            ax.plot(df_resampled.index, df_resampled['spread_2'],
                   label='B买→A卖', alpha=0.8, linewidth=1)
            ax.axhline(y=1.0, color='green', linestyle='--', alpha=0.7, label='盈利线')
            ax.axhline(y=-1.0, color='green', linestyle='--', alpha=0.7)
            ax.fill_between(df_resampled.index, 1.0, df_resampled['spread_1'],
                           where=(df_resampled['spread_1'] > 1.0),
                           alpha=0.3, color='green', label='盈利区域1')
            ax.fill_between(df_resampled.index, -1.0, df_resampled['spread_2'],
                           where=(df_resampled['spread_2'] > 1.0),
                           alpha=0.3, color='red', label='盈利区域2')

            ax.set_title(f'{symbol} Spread Time Series')
            ax.set_xlabel('Time')
            ax.set_ylabel('Spread (USD)')
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.data_dir / 'spread_timeseries.png', dpi=300, bbox_inches='tight')
        print(f"💾 时间序列图保存: {self.data_dir / 'spread_timeseries.png'}")

    def arbitrage_opportunities(self, min_spread: float = 1.0):
        """套利机会分析"""
        print(f"\n" + "="*50)
        print(f"💰 套利机会分析 (最小价差: {min_spread})")
        print("="*50)

        for symbol, df in self.data.items():
            print(f"\n🔸 {symbol} 套利机会:")

            # 方向1套利机会
            opp_1 = df[df['spread_1'] > min_spread].copy()
            if len(opp_1) > 0:
                print(f"   A买→B卖套利:")
                print(f"     机会次数: {len(opp_1)}")
                print(f"     平均价差: {opp_1['spread_1'].mean():.2f}")
                print(f"     最大价差: {opp_1['spread_1'].max():.2f}")
                print(f"     持续时间: 平均 {self._calculate_duration(opp_1):.1f}秒")

            # 方向2套利机会
            opp_2 = df[df['spread_2'] > min_spread].copy()
            if len(opp_2) > 0:
                print(f"   B买→A卖套利:")
                print(f"     机会次数: {len(opp_2)}")
                print(f"     平均价差: {opp_2['spread_2'].mean():.2f}")
                print(f"     最大价差: {opp_2['spread_2'].max():.2f}")
                print(f"     持续时间: 平均 {self._calculate_duration(opp_2):.1f}秒")

            # 保存套利机会详情
            all_opportunities = pd.concat([
                opp_1[['datetime', 'spread_1']].rename(columns={'spread_1': 'spread'}).assign(direction='A买→B卖'),
                opp_2[['datetime', 'spread_2']].rename(columns={'spread_2': 'spread'}).assign(direction='B买→A卖')
            ]).sort_values('datetime')

            if len(all_opportunities) > 0:
                filename = self.data_dir / f'arbitrage_opportunities_{symbol}.csv'
                all_opportunities.to_csv(filename, index=False)
                print(f"   💾 套利机会详情保存: {filename}")

    def _calculate_duration(self, df):
        """计算套利机会平均持续时间"""
        if len(df) <= 1:
            return 0

        durations = []
        current_start = df.iloc[0]['datetime']

        for i in range(1, len(df)):
            time_gap = (df.iloc[i]['datetime'] - df.iloc[i-1]['datetime']).total_seconds()
            if time_gap > 10:  # 超过10秒认为是新的机会
                durations.append((df.iloc[i-1]['datetime'] - current_start).total_seconds())
                current_start = df.iloc[i]['datetime']

        # 添加最后一个机会的持续时间
        durations.append((df.iloc[-1]['datetime'] - current_start).total_seconds())

        return np.mean(durations) if durations else 0

    def correlation_analysis(self):
        """相关性分析"""
        print(f"\n" + "="*50)
        print("🔗 相关性分析")
        print("="*50)

        if len(self.data) < 2:
            print("需要至少2个交易对进行相关性分析")
            return

        # 合并所有数据进行相关性分析
        correlation_data = {}
        base_time = None

        for symbol, df in self.data.items():
            # 重采样为分钟数据
            df_resampled = df.set_index('datetime').resample('1T').mean()
            correlation_data[f'{symbol}_spread_1'] = df_resampled['spread_1']
            correlation_data[f'{symbol}_spread_2'] = df_resampled['spread_2']
            correlation_data[f'{symbol}_best'] = df_resampled['best_spread']

        corr_df = pd.DataFrame(correlation_data)
        correlation_matrix = corr_df.corr()

        # 绘制相关性热力图
        plt.figure(figsize=(12, 10))
        sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', center=0,
                   square=True, linewidths=0.5)
        plt.title('Spread Correlation Matrix')
        plt.tight_layout()
        plt.savefig(self.data_dir / 'correlation_matrix.png', dpi=300, bbox_inches='tight')
        print(f"💾 相关性矩阵图保存: {self.data_dir / 'correlation_matrix.png'}")

        # 打印关键相关性
        print("\n关键相关性系数:")
        symbols = list(self.data.keys())
        if len(symbols) >= 2:
            for i in range(len(symbols)):
                for j in range(i+1, len(symbols)):
                    corr_coef = correlation_matrix.loc[f'{symbols[i]}_best', f'{symbols[j]}_best']
                    print(f"   {symbols[i]} vs {symbols[j]}: {corr_coef:.3f}")

    def generate_report(self):
        """生成分析报告"""
        print(f"\n" + "="*50)
        print("📋 生成分析报告")
        print("="*50)

        report_file = self.data_dir / 'analysis_report.txt'

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"价差数据分析报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"="*50 + "\n\n")

            for symbol, df in self.data.items():
                f.write(f"{symbol} 分析结果:\n")
                f.write(f"-"*30 + "\n")

                # 基础统计
                f.write(f"数据概况:\n")
                f.write(f"  记录条数: {len(df):,}\n")
                f.write(f"  时间范围: {df['datetime'].min()} ~ {df['datetime'].max()}\n")

                # 价差统计
                f.write(f"\n价差统计:\n")
                f.write(f"  方向1均值: {df['spread_1'].mean():.2f} ± {df['spread_1'].std():.2f}\n")
                f.write(f"  方向2均值: {df['spread_2'].mean():.2f} ± {df['spread_2'].std():.2f}\n")
                f.write(f"  最佳价差均值: {df['best_spread'].mean():.2f} ± {df['best_spread'].std():.2f}\n")

                # 套利机会
                profitable_1 = (df['spread_1'] > 1.0).sum()
                profitable_2 = (df['spread_2'] > 1.0).sum()
                f.write(f"\n套利机会 (>1美元):\n")
                f.write(f"  方向1: {profitable_1} 次 ({profitable_1/len(df)*100:.1f}%)\n")
                f.write(f"  方向2: {profitable_2} 次 ({profitable_2/len(df)*100:.1f}%)\n")
                f.write(f"  总计: {profitable_1 + profitable_2} 次 ({(profitable_1 + profitable_2)/len(df)*100:.1f}%)\n")

                f.write(f"\n" + "="*50 + "\n\n")

        print(f"💾 分析报告保存: {report_file}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='价差数据分析工具')
    parser.add_argument('--data-dir', default='spread_data', help='数据目录路径')
    parser.add_argument('--symbol', help='指定分析的交易对')
    parser.add_argument('--days', type=int, help='分析最近N天的数据')
    parser.add_argument('--min-spread', type=float, default=1.0, help='最小套利价差')

    args = parser.parse_args()

    print("""
╔═══════════════════════════════════════╗
║      价差数据分析器 - analyze.py       ║
║        套利机会与规律分析              ║
╚═══════════════════════════════════════╝
    """)

    try:
        analyzer = SpreadAnalyzer(args.data_dir)

        # 加载数据
        if not analyzer.load_data(symbol=args.symbol, days=args.days):
            return

        # 执行各种分析
        analyzer.basic_statistics()
        analyzer.spread_distribution()
        analyzer.time_series_analysis()
        analyzer.arbitrage_opportunities(min_spread=args.min_spread)
        analyzer.correlation_analysis()
        analyzer.generate_report()

        print(f"\n✅ 分析完成！结果保存在: {analyzer.data_dir}")

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()