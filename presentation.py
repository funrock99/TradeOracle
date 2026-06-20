import math
import os
from typing import Optional

import matplotlib
matplotlib.use('Agg') # Ensure non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.patches as mpatches
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from signals import StockSignalEngine

import matplotlib.font_manager as fm

# --- 全域字型設定強化 (解決 Linux 豆腐塊問題且避免多執行緒競爭) ---
possible_linux_fonts = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-TC-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansTC-Regular.otf",
]
win_font = "C:/Windows/Fonts/msjh.ttc"

font_found = False
for font_path in possible_linux_fonts:
    if os.path.exists(font_path):
        fe = fm.FontEntry(fname=font_path, name='Noto Sans CJK TC')
        fm.fontManager.ttflist.insert(0, fe)
        plt.rcParams['font.family'] = fe.name
        font_found = True
        break

if not font_found:
    if os.path.exists(win_font):
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
    else:
        plt.rcParams['font.sans-serif'] = ['Noto Sans CJK TC', 'Microsoft JhengHei', 'sans-serif']

plt.rcParams['axes.unicode_minus'] = False
# -------------------------------------------------------------

class StockExpertSystem(StockSignalEngine):
    def __init__(self, symbol: Optional[str] = None, **kwargs):
        super().__init__(symbol)

    def _format_level(self, value: Optional[float]) -> str:
        return "---" if value is None or math.isnan(value) else f"{value:.2f}"


    def get_line_report(self) -> str:
        snapshot = self.build_snapshot()
        trend_emoji = "📈" if snapshot.change > 0 else "📉"
        
        # 格式化日期為 YYYY/MM/DD
        display_date = snapshot.last_date.replace("-", "/")
        
        # 盤中標籤動態切換
        price_label = "最新價格" if snapshot.is_intraday else "收盤價"
        
        # 預先格式化指標字串，避免 f-string 語法錯誤
        rsi_str = f"{snapshot.rsi14:.1f}" if snapshot.rsi14 is not None else "---"
        kd_k_str = f"{snapshot.kd_k:.1f}" if snapshot.kd_k is not None else "---"
        kd_d_str = f"{snapshot.kd_d:.1f}" if snapshot.kd_d is not None else "---"
        
        report = (
            f"【{snapshot.stock_name} ({snapshot.symbol}) 專家分析】\n"
            f"📅 最後交易日: {display_date}\n"
            f"💰 {price_label}: {snapshot.close:.2f} ({trend_emoji} {snapshot.change:+.2f} / {snapshot.pct_change:+.2f}%)\n"
            f"📊 成交量: {snapshot.volume/1000:,.0f} 張 (5MA: {snapshot.vma5/1000:,.0f} 張)\n"
            f"--------------------------\n"
            f"🛡️ 關鍵價位:\n"
            f"   - 壓力: {self._format_level(snapshot.resistance)}\n"
            f"   - 支撐: {self._format_level(snapshot.support)}\n"
            f"   - 停損: {self._format_level(snapshot.stop_loss)}\n"
            f"--------------------------\n"
            f"💡 專家建議:\n"
            f"   {snapshot.advice_text}\n\n"
            f"⚡ 主力動向:\n"
            f"   {snapshot.force_alert[0]}\n\n"
            f"⚠️ 風險摘要:\n"
            f"   {snapshot.risk_note}\n"
            f"--------------------------\n"
            f"🔍 技術指標:\n"
            f"   - RSI14: {rsi_str}\n"
            f"   - KD: {kd_k_str}/{kd_d_str}\n"
            f"   - 趨勢: {snapshot.trend_status}\n"
            f"   - 20日突破: {snapshot.breakout_status}"
        )
        return report

    def export_line_chart(self) -> str:
        """導出適合 Line 顯示的靜態圖表 (PNG)"""
        if self.df is None or self.df.empty:
            raise ValueError("尚未載入資料，無法輸出圖表。")

        # 僅取最近 60 筆資料
        plot_df = self.df.tail(60).copy()
        
        # 為了計算漲跌，我們需要前一日收盤價
        plot_df = plot_df.copy()
        plot_df['Prev_Close'] = plot_df['Close'].shift(1)
        
        # 補足第一筆的 Prev_Close (從完整 df 找，若無則用 Open 代替)
        first_date = plot_df.index[0]
        full_df_idx = self.df.index.get_loc(first_date)
        if full_df_idx > 0:
            plot_df.at[first_date, 'Prev_Close'] = self.df.iloc[full_df_idx - 1]['Close']
        else:
            plot_df.at[first_date, 'Prev_Close'] = plot_df.at[first_date, 'Open']

        fig = Figure(figsize=(10, 8))
        canvas = FigureCanvasAgg(fig)
        ax1, ax2 = fig.subplots(2, 1, gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        
        # 繪製 K 線
        for i in range(len(plot_df)):
            row = plot_df.iloc[i]
            # 台灣慣例: 只要比昨收高就是紅色 (漲)，比昨收低就是綠色 (跌)
            # 這樣能確保與 GUI/CLI 顯示的「▲ 漲跌」顏色一致
            color = 'red' if row['Close'] >= row['Prev_Close'] else 'green'
            
            # 影線
            ax1.plot([i, i], [row['Low'], row['High']], color=color, linewidth=1)
            # 實體 (K線實體反映的是開收盤關係，但顏色遵循漲跌)
            width = 0.6
            rect = mpatches.Rectangle((i - width/2, min(row['Open'], row['Close'])), 
                                      width, abs(row['Open'] - row['Close']), 
                                      facecolor=color, edgecolor=color)
            ax1.add_patch(rect)

        # 均線 (加入安全性檢查，避免欄位不存在時報錯)
        if 'SMA_5' in plot_df.columns:
            ax1.plot(range(len(plot_df)), plot_df['SMA_5'], label='MA5', color='orange', alpha=0.7)
        if 'SMA_20' in plot_df.columns:
            ax1.plot(range(len(plot_df)), plot_df['SMA_20'], label='MA20', color='cyan', alpha=0.7)
        if 'SMA_60' in plot_df.columns:
            ax1.plot(range(len(plot_df)), plot_df['SMA_60'], label='MA60', color='purple', alpha=0.7)
        
        ax1.set_title(f"{self.stock_name} ({self.symbol}) 專家分析圖表", fontsize=16)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 成交量 (與 K 線顏色一致，遵循昨收漲跌)
        ax2.bar(range(len(plot_df)), plot_df['Volume'], 
                color=['red' if r['Close'] >= r['Prev_Close'] else 'green' for _, r in plot_df.iterrows()], 
                alpha=0.7)
        ax2.set_ylabel("成交量")
        ax2.grid(True, alpha=0.3)

        # 設定 X 軸標籤 (日期)
        step = max(1, len(plot_df) // 10)
        ax2.set_xticks(range(0, len(plot_df), step))
        ax2.set_xticklabels([plot_df.index[i].strftime('%m-%d') for i in range(0, len(plot_df), step)], rotation=45)

        fig.tight_layout()
        
        # 取得資料最後交易日期 (正規化為日期，避免時區造成誤差)
        last_data_ts = self.df.index[-1]
        import pandas as pd
        if hasattr(last_data_ts, 'date'):
            last_date_str = last_data_ts.strftime("%Y%m%d")
        else:
            last_date_str = pd.to_datetime(last_data_ts).strftime("%Y%m%d")
            
        filename = f"chart_{self.symbol.replace('.', '_')}_{last_date_str}.png"
        chart_path = os.path.join(self.report_dir, filename)
        
        # 確保資料夾存在
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)
            
        fig.savefig(chart_path, dpi=150)
        return chart_path

    def export_plotly_report(self) -> str:
        if self.df is None or self.df.empty:
            raise ValueError("尚未載入資料，無法輸出報告。")

        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.15, 0.15, 0.2],
            subplot_titles=("K線與均線", "成交量", "RSI", "MACD"),
        )
        fig.add_trace(
            go.Candlestick(
                x=self.df.index,
                open=self.df["Open"],
                high=self.df["High"],
                low=self.df["Low"],
                close=self.df["Close"],
                name="K線",
                increasing_line_color="red",
                decreasing_line_color="green",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=self.df.index, y=self.df["SMA_5"], line=dict(color="yellow", width=1), name="MA5"),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=self.df.index, y=self.df["SMA_20"], line=dict(color="cyan", width=1), name="MA20"),
            row=1,
            col=1,
        )
        if "SMA_60" in self.df.columns:
            fig.add_trace(
                go.Scatter(x=self.df.index, y=self.df["SMA_60"], line=dict(color="purple", width=1), name="MA60"),
                row=1,
                col=1,
            )

        # 成交量顏色 (漲紅跌綠，相較於昨收)
        # 確保與 CLI/GUI 的漲跌判定邏輯一致
        df_vol = self.df.copy()
        df_vol['Prev_Close'] = df_vol['Close'].shift(1)
        # 第一筆資料昨收用開盤價代替
        df_vol.loc[df_vol.index[0], 'Prev_Close'] = df_vol.loc[df_vol.index[0], 'Open']
        
        vol_colors = [
            "red" if row["Close"] >= row["Prev_Close"] else "green"
            for _, row in df_vol.iterrows()
        ]
        fig.add_trace(
            go.Bar(
                x=self.df.index,
                y=self.df["Volume"],
                name="成交量",
                marker_color=vol_colors,
            ),
            row=2,
            col=1,
        )
        fig.add_trace(go.Scatter(x=self.df.index, y=self.df["RSI_14"], name="RSI"), row=3, col=1)
        fig.add_trace(go.Bar(x=self.df.index, y=self.df["MACDh_12_26_9"], name="MACD柱"), row=4, col=1)
        if "ATRr_14" in self.df.columns:
            fig.add_trace(
                go.Scatter(x=self.df.index, y=self.df["ATRr_14"], name="ATR14", line=dict(color="magenta", width=1)),
                row=4,
                col=1,
            )

        fig.update_layout(
            template="plotly_dark",
            title=f"{self.stock_name} ({self.symbol}) 專家分析報告",
            xaxis_rangeslider_visible=False,
            height=900,
        )

        last_date_str = self.df.index[-1].strftime("%Y%m%d")
        filename = f"report_{self.symbol.replace('.', '_')}_{last_date_str}.html"
        self.report_path = os.path.join(self.report_dir, filename)
        fig.write_html(self.report_path)
        return self.report_path
