import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd
import pandas_ta as ta

from data import StockDataManager


@dataclass
class AnalysisSnapshot:
    symbol: str
    stock_name: str
    last_date: str
    close: float
    change: float
    pct_change: float
    volume: float
    vma5: float
    atr14: Optional[float]
    adx14: Optional[float]
    di_plus: Optional[float]
    di_minus: Optional[float]
    relative_strength_20d: Optional[float]
    benchmark_name: str
    breakout_high_20: Optional[float]
    breakout_low_20: Optional[float]
    breakout_status: str
    risk_note: str
    resistance: Optional[float]
    support: Optional[float]
    stop_loss: Optional[float]
    rsi14: Optional[float]
    kd_k: Optional[float]
    kd_d: Optional[float]
    force_alert: Tuple[str, str]
    divergence: Tuple[str, str]
    advice_text: str
    advice_color: str
    is_bullish: bool
    trend_status: str
    is_intraday: bool = False


class StockSignalEngine(StockDataManager):
    def analyze(self) -> None:
        if self.df is None or self.df.empty:
            raise ValueError("尚未載入資料，無法分析。")

        df = self.df.copy()
        # 確保資料筆數足以計算指標，否則 pandas-ta 可能不產生欄位
        try:
            df.ta.sma(length=5, append=True)
            df.ta.sma(length=20, append=True)
            df.ta.sma(length=60, append=True)
            df.ta.rsi(length=14, append=True)
            df.ta.macd(append=True)
            df.ta.stoch(append=True)
            df.ta.atr(length=14, append=True)
            df.ta.adx(length=14, append=True)
        except Exception as e:
            print(f">>> 指標計算部分失敗: {e}")

        df["VMA_5"] = df["Volume"].rolling(window=5, min_periods=1).mean()
        df["HIGH_20"] = df["High"].rolling(window=20, min_periods=1).max().shift(1)
        df["LOW_20"] = df["Low"].rolling(window=20, min_periods=1).min().shift(1)
        self.df = df

        recent_high = self.df.tail(20)["High"].max()
        self.resistance = self.round_to_tick(recent_high)
        self.support = self.round_to_tick(self._latest_value("SMA_20"))
        atr14 = self._latest_value("ATRr_14")
        sma60 = self._latest_value("SMA_60")
        atr_stop = None
        if atr14 is not None:
            atr_stop = float(self.df["Close"].iloc[-1]) - (atr14 * 1.5)
        
        # 停損參考優先順序: ATR 停損 > SMA60 > SMA20
        fallback_stop = sma60 if sma60 is not None else self._latest_value("SMA_20")
        self.stop_loss = self.round_to_tick(atr_stop if atr_stop is not None else fallback_stop)

    def _get_trend_status(self, last_row: pd.Series) -> str:
        sma5 = last_row.get("SMA_5")
        sma20 = last_row.get("SMA_20")
        sma60 = last_row.get("SMA_60")
        
        if not all(pd.notna(v) for v in [sma5, sma20, sma60]):
            return "資料不足"
            
        # 多頭強勢: 5 > 20 > 60
        if sma5 > sma20 > sma60:
            return "多頭強勢"
        # 多頭拉回: 20 > 60 但 5 < 20
        if sma20 > sma60 and sma5 < sma20:
            return "多頭拉回"
        # 空頭強勢: 5 < 20 < 60
        if sma5 < sma20 < sma60:
            return "空頭強勢"
        # 空頭反彈: 20 < 60 但 5 > 20
        if sma20 < sma60 and sma5 > sma20:
            return "空頭反彈"
        # 均線糾結或轉折中
        return "盤整/轉折"

    def _latest_value(self, column: str) -> Optional[float]:
        if self.df is None or column not in self.df.columns:
            return None

        series = self.df[column].dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])

    def _require_snapshot_ready(self) -> None:
        if self.df is None or len(self.df) < 2:
            raise ValueError("交易資料不足，至少需要兩筆有效日線資料。")

    def _compute_relative_strength_20d(self) -> Optional[float]:
        if self.df is None or self.benchmark_df is None:
            return None

        stock_close = self.df[["Close"]].rename(columns={"Close": "stock_close"}).copy()
        benchmark_close = self.benchmark_df[["Close"]].rename(columns={"Close": "benchmark_close"}).copy()

        stock_close.index = pd.to_datetime(stock_close.index)
        benchmark_close.index = pd.to_datetime(benchmark_close.index)
        if stock_close.index.tz is not None:
            stock_close.index = stock_close.index.tz_localize(None)
        if benchmark_close.index.tz is not None:
            benchmark_close.index = benchmark_close.index.tz_localize(None)
        joined = stock_close.join(benchmark_close, how="inner").dropna()
        if len(joined) < 21:
            return None

        latest = joined.iloc[-1]
        past = joined.iloc[-21]
        stock_return = (float(latest["stock_close"]) / float(past["stock_close"])) - 1
        benchmark_return = (float(latest["benchmark_close"]) / float(past["benchmark_close"])) - 1
        return stock_return - benchmark_return

    def _get_breakout_status(self, last_row: pd.Series) -> str:
        high_20 = last_row.get("HIGH_20")
        low_20 = last_row.get("LOW_20")
        close = last_row.get("Close")
        vma5 = last_row.get("VMA_5")
        volume = last_row.get("Volume")

        if not all(pd.notna(v) for v in [high_20, low_20, close]):
            return "資料不足"

        if pd.notna(vma5) and pd.notna(volume) and volume >= vma5:
            if close > high_20:
                return "20日突破"
            if close < low_20:
                return "20日跌破"
        
        # 計算區間位置百分比 (0% 為下緣, 100% 為上緣)
        range_size = high_20 - low_20
        if range_size > 0:
            pos_pct = (close - low_20) / range_size
            if pos_pct >= 0.8:
                return "區間震盪 (接近上緣)"
            if pos_pct <= 0.2:
                return "區間震盪 (接近下緣)"
        
        return "區間內震盪"

    def _get_risk_note(self, last_row: pd.Series) -> str:
        atr14 = last_row.get("ATRr_14")
        close = last_row.get("Close")
        adx14 = last_row.get("ADX_14")
        if pd.isna(atr14) or pd.isna(close) or float(close) == 0:
            return "風險資料不足"

        atr_pct = (float(atr14) / float(close)) * 100
        if atr_pct >= 4:
            risk = "波動擴張"
        elif atr_pct <= 2:
            risk = "波動溫和"
        else:
            risk = "波動中性"

        if pd.notna(adx14) and float(adx14) >= 25:
            return f"{risk} / 趨勢市場"
        if pd.notna(adx14) and float(adx14) < 20:
            return f"{risk} / 盤整市場"
        return risk

    def get_volume_analysis(self, last_row: pd.Series) -> Tuple[Tuple[str, str], Tuple[str, str]]:
        self._require_snapshot_ready()
        prev_close = float(self.df.iloc[-2]["Close"])
        vma5 = last_row.get("VMA_5")
        volume = float(last_row["Volume"])
        close = float(last_row["Close"])

        force_alert = ("量能平穩", "white")
        if pd.notna(vma5):
            if volume > vma5 * 2.0:
                force_alert = ("主力異常爆量", "bold red")
            elif volume > vma5 * 1.5:
                force_alert = (
                    ("主力顯著進場", "red") if close > prev_close else ("主力顯著出貨", "green")
                )

        recent_5 = self.df.tail(5)
        divergence = ("量價同步", "white")
        if pd.notna(vma5):
            is_high = close >= float(recent_5["Close"].max())
            is_low = close <= float(recent_5["Close"].min())
            if is_high and volume < vma5:
                divergence = ("頂背離 (價高量縮)", "bold yellow")
            elif is_low and volume < vma5:
                divergence = ("底背離 (價低量縮)", "bold cyan")

        return force_alert, divergence

    def _evaluate_signals(self, last_row: pd.Series) -> Dict[str, object]:
        sma5 = last_row.get("SMA_5")
        sma20 = last_row.get("SMA_20")
        sma60 = last_row.get("SMA_60")
        rsi14 = last_row.get("RSI_14")
        kd_k = last_row.get("STOCHk_14_3_3")
        kd_d = last_row.get("STOCHd_14_3_3")
        adx14 = last_row.get("ADX_14")
        di_plus = last_row.get("DMP_14")
        di_minus = last_row.get("DMN_14")
        relative_strength_20d = self._compute_relative_strength_20d()
        breakout_status = self._get_breakout_status(last_row)
        force_alert, divergence = self.get_volume_analysis(last_row)

        is_bullish = all(pd.notna(value) for value in [sma5, sma20, sma60]) and sma5 > sma20 > sma60
        is_ma_positive = pd.notna(sma5) and pd.notna(sma20) and sma5 > sma20
        rsi_hot = pd.notna(rsi14) and rsi14 > 70
        rsi_low = pd.notna(rsi14) and rsi14 < 30
        kd_gold = pd.notna(kd_k) and pd.notna(kd_d) and kd_k > kd_d
        adx_trending = pd.notna(adx14) and adx14 >= 25
        adx_ranging = pd.notna(adx14) and adx14 < 20
        di_bullish = pd.notna(di_plus) and pd.notna(di_minus) and di_plus > di_minus
        di_bearish = pd.notna(di_plus) and pd.notna(di_minus) and di_minus > di_plus
        rs_positive = relative_strength_20d is not None and relative_strength_20d > 0
        rs_negative = relative_strength_20d is not None and relative_strength_20d < 0
        breakout_bullish = breakout_status == "20日突破"
        breakout_bearish = breakout_status == "20日跌破"
        bearish_divergence = "頂背離" in divergence[0]
        bullish_divergence = "底背離" in divergence[0]
        strong_accumulation = "主力顯著進場" in force_alert[0] or "爆量" in force_alert[0]
        strong_distribution = "主力顯著出貨" in force_alert[0]

        trend_score = 2 if is_bullish else 1 if is_ma_positive else 0
        rsi_score = 1 if pd.notna(rsi14) and (30 < rsi14 <= 65 or rsi_low) else 0
        kd_score = 1 if kd_gold else 0
        volume_score = 1 if strong_accumulation else 0
        total_score = trend_score + rsi_score + kd_score + volume_score

        return {
            "trend_score": trend_score,
            "rsi_score": rsi_score,
            "kd_score": kd_score,
            "volume_score": volume_score,
            "total_score": total_score,
            "is_bullish": is_bullish,
            "is_ma_positive": is_ma_positive,
            "rsi_hot": rsi_hot,
            "rsi_low": rsi_low,
            "kd_gold": kd_gold,
            "adx_trending": adx_trending,
            "adx_ranging": adx_ranging,
            "di_bullish": di_bullish,
            "di_bearish": di_bearish,
            "rs_positive": rs_positive,
            "rs_negative": rs_negative,
            "breakout_bullish": breakout_bullish,
            "breakout_bearish": breakout_bearish,
            "relative_strength_20d": relative_strength_20d,
            "breakout_status": breakout_status,
            "bearish_divergence": bearish_divergence,
            "bullish_divergence": bullish_divergence,
            "strong_accumulation": strong_accumulation,
            "strong_distribution": strong_distribution,
        }

    def get_action_advice(self, last_row: pd.Series) -> Tuple[str, str]:
        signal = self._evaluate_signals(last_row)
        rating = max(1, min(5, signal["total_score"]))

        if signal["rsi_hot"]:
            return "建議觀望 (短線過熱，等待回檔)", "orange"
        if signal["breakout_bearish"] and signal["adx_trending"] and signal["di_bearish"]:
            return "建議保守 (20日跌破且空方趨勢增強)", "gray"
        if signal["breakout_bullish"] and signal["adx_trending"] and signal["rs_positive"]:
            return "突破追蹤 (20日突破，趨勢與相對強弱同步轉強)", "red"
        if rating >= 4:
            if signal["adx_trending"] and signal["rs_positive"]:
                return "建議買進 (多頭結構完整，趨勢與相對強弱同步偏多)", "red"
            return "建議買進 (多頭結構完整，可分批順勢布局)", "red"
        if rating == 3:
            if signal["is_bullish"] and not signal["bearish_divergence"]:
                if signal["adx_ranging"]:
                    return "偏多觀察 (均線偏多，但仍屬盤整，避免過度追價)", "blue"
                return "偏多觀察 (等待轉強或回踩支撐再布局)", "blue"
            return "中性觀察 (訊號尚未一致，避免追價)", "blue"
        if signal["rsi_low"] and signal["bullish_divergence"]:
            return "留意短線反彈 (僅適合輕倉試單)", "orange"
        if rating == 2 and signal["is_bullish"]:
            return "建議觀望 (趨勢仍偏多，但動能不足)", "gray"
        return "建議觀望 (盤勢偏弱，保守待變)", "gray"

    def build_snapshot(self) -> AnalysisSnapshot:
        self._require_snapshot_ready()
        last_row = self.df.iloc[-1]
        prev_row = self.df.iloc[-2]
        change = float(last_row["Close"] - prev_row["Close"])
        pct_change = (change / float(prev_row["Close"])) * 100
        force_alert, divergence = self.get_volume_analysis(last_row)
        advice_text, advice_color = self.get_action_advice(last_row)
        relative_strength_20d = self._compute_relative_strength_20d()
        breakout_status = self._get_breakout_status(last_row)
        risk_note = self._get_risk_note(last_row)
        trend_status = self._get_trend_status(last_row)

        sma5 = last_row.get("SMA_5")
        sma20 = last_row.get("SMA_20")
        sma60 = last_row.get("SMA_60")
        is_bullish = all(pd.notna(value) for value in [sma5, sma20, sma60]) and sma5 > sma20 > sma60

        return AnalysisSnapshot(
            symbol=self.symbol,
            stock_name=self.stock_name,
            last_date=self.df.index[-1].strftime("%Y-%m-%d"),
            close=float(last_row["Close"]),
            change=change,
            pct_change=pct_change,
            volume=float(last_row["Volume"]),
            vma5=float(last_row["VMA_5"]) if pd.notna(last_row["VMA_5"]) else math.nan,
            atr14=float(last_row["ATRr_14"]) if pd.notna(last_row.get("ATRr_14")) else None,
            adx14=float(last_row["ADX_14"]) if pd.notna(last_row.get("ADX_14")) else None,
            di_plus=float(last_row["DMP_14"]) if pd.notna(last_row.get("DMP_14")) else None,
            di_minus=float(last_row["DMN_14"]) if pd.notna(last_row.get("DMN_14")) else None,
            relative_strength_20d=relative_strength_20d,
            benchmark_name=self.benchmark_name,
            breakout_high_20=float(last_row["HIGH_20"]) if pd.notna(last_row.get("HIGH_20")) else None,
            breakout_low_20=float(last_row["LOW_20"]) if pd.notna(last_row.get("LOW_20")) else None,
            breakout_status=breakout_status,
            risk_note=risk_note,
            resistance=self.resistance,
            support=self.support,
            stop_loss=self.stop_loss,
            rsi14=float(last_row["RSI_14"]) if pd.notna(last_row.get("RSI_14")) else None,
            kd_k=float(last_row["STOCHk_14_3_3"]) if pd.notna(last_row.get("STOCHk_14_3_3")) else None,
            kd_d=float(last_row["STOCHd_14_3_3"]) if pd.notna(last_row.get("STOCHd_14_3_3")) else None,
            force_alert=force_alert,
            divergence=divergence,
            advice_text=advice_text,
            advice_color=advice_color,
            is_bullish=is_bullish,
            trend_status=trend_status,
            is_intraday=self.is_intraday,
        )
