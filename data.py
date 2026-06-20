import json
import os
import random
import time
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests
import yfinance as yf
import twstock
from requests.exceptions import SSLError
from urllib3.exceptions import InsecureRequestWarning


REPORT_DIR = "reports"
CACHE_DIR = "cache"


# 多組 User-Agent 輪替
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"
]

OFFICIAL_DATA_HOSTS = {"www.twse.com.tw", "www.tpex.org.tw"}


def is_valid_symbol(symbol: str) -> bool:
    """檢查是否為合法的台股代碼 (存在於 twstock 字典中)"""
    import twstock
    clean_code = symbol.upper().replace('.TW', '').replace('.TWO', '')
    return clean_code in twstock.codes


def get_last_data_settlement_time(now_tw: datetime) -> datetime:
    """取得距離 now_tw 最近的一次「盤後資料確定時間」(考量官方延遲，設定為交易日的 15:00)"""
    dt = now_tw
    if dt.time() < datetime(2000, 1, 1, 15, 0).time():
        dt -= timedelta(days=1)
        
    while dt.weekday() > 4: # 5: Sat, 6: Sun
        dt -= timedelta(days=1)
        
    return dt.replace(hour=15, minute=0, second=0, microsecond=0)


def is_cache_valid(updated_at: datetime) -> bool:
    """
    Line Bot 報表快取有效性判定：
    1. 1 小時內的快取永遠有效 (盤中滾動更新)。
    2. 盤後時間建立的快取，在下一個交易日開盤 (09:00) 前皆有效，無需頻繁更新。
    """
    from datetime import timezone, timedelta
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=tw_tz)
    else:
        updated_at = updated_at.astimezone(tw_tz)
        
    # 跨越 13:30 (一般交易收盤) 邊界：強制失效以更新「收盤價」文字與狀態
    if updated_at.date() == now.date() and now.weekday() < 5:
        time_1330 = now.replace(hour=13, minute=30, second=0, microsecond=0)
        if updated_at < time_1330 and now >= time_1330:
            return False
            
    # 跨越 14:30 (盤後定價與零股結算) 邊界：強制失效以抓取最終盤後成交量
    if updated_at.date() == now.date() and now.weekday() < 5:
        time_1430 = now.replace(hour=14, minute=30, second=0, microsecond=0)
        if updated_at < time_1430 and now >= time_1430:
            return False

    if now - updated_at < timedelta(hours=1):
        return True
        
    last_settlement = get_last_data_settlement_time(now)
    
    if updated_at >= last_settlement:
        next_open = last_settlement + timedelta(days=1)
        while next_open.weekday() > 4:
            next_open += timedelta(days=1)
        next_open = next_open.replace(hour=9, minute=0, second=0, microsecond=0)
        
        if now < next_open:
            return True
            
    return False

def is_history_cache_valid(updated_at: datetime) -> bool:
    """
    歷史資料 CSV 快取判定 (Yahoo Finance):
    只要快取包含「最近一次盤後結算」的資料即視為有效。
    盤中最新的報價會由 twstock 即時補足，不需在盤中反覆呼叫 Yahoo Finance 抓取歷史底稿。
    """
    from datetime import timezone, timedelta
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=tw_tz)
    else:
        updated_at = updated_at.astimezone(tw_tz)
        
    # 如果快取是在今日盤中(14:30前)建立，但現在已經超過盤後定價時間(14:30)，
    # 則強制歷史快取失效，以便重新抓取包含盤後定價與零股的 Yahoo Finance 歷史資料
    if updated_at.date() == now.date() and now.weekday() < 5:
        close_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
        if updated_at < close_time and now >= close_time:
            return False

    last_settlement = get_last_data_settlement_time(now)
    
    # 只要快取建立時間 >= 最近一次結算時間，就完全有效！
    return updated_at >= last_settlement



class StockDataManager:
    def __init__(self, symbol: Optional[str] = None):
        self.symbol = symbol.upper() if symbol else ""
        self.mapping = self._load_mapping()
        self.df: Optional[pd.DataFrame] = None
        self.benchmark_df: Optional[pd.DataFrame] = None
        self.benchmark_name = "大盤基準"
        self.stock_name = ""
        self.report_path = ""
        self.report_dir = REPORT_DIR
        self.cache_dir = CACHE_DIR
        self.is_intraday = False
        os.makedirs(self.report_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_random_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def _load_mapping(self) -> dict:
        import twstock
        mapping = {}
        try:
            for code, info in twstock.codes.items():
                if info.type == '股票' and len(code) == 4 and code.isdigit():
                    mapping[code] = info.name.strip()
        except Exception:
            pass
        return mapping

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.isdigit() and len(normalized) >= 4:
            return f"{normalized}.TW"
        return normalized

    def _request_json(self, url: str) -> dict:
        request_kwargs = {
            "headers": {"User-Agent": self._get_random_agent()},
            "timeout": 10,
        }

        try:
            response = requests.get(url, **request_kwargs)
        except SSLError:
            host = urlparse(url).hostname or ""
            if host not in OFFICIAL_DATA_HOSTS:
                raise
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                response = requests.get(url, verify=False, **request_kwargs)

        response.raise_for_status()
        return response.json()

    def _get_cache_path(self, symbol: str) -> str:
        return os.path.join(self.cache_dir, f"{symbol.replace('.', '_')}.csv")

    def _save_to_cache(self, symbol: str, df: pd.DataFrame):
        try:
            cache_path = self._get_cache_path(symbol)
            df.to_csv(cache_path)
        except Exception:
            pass

    def _load_from_cache(self, symbol: str) -> Optional[pd.DataFrame]:
        cache_path = self._get_cache_path(symbol)
        if not os.path.exists(cache_path):
            return None
        
        from datetime import timezone
        mtime = os.path.getmtime(cache_path)
        updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
        
        if not is_history_cache_valid(updated_at):
            return None
            
        try:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if not df.empty:
                return df
        except Exception:
            pass
        return None

    def _fetch_yfinance_history(self, symbol: str) -> Tuple[str, yf.Ticker, pd.DataFrame]:
        # 1. 嘗試讀取快取
        cached_df = self._load_from_cache(symbol)
        if cached_df is not None:
            return symbol, yf.Ticker(symbol), cached_df

        # 2. 準備抓取
        clean_symbol = symbol.split(".")[0]
        candidates = []
        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            other = symbol.replace(".TW", ".TWO") if symbol.endswith(".TW") else symbol.replace(".TWO", ".TW")
            candidates = [symbol, other]
        else:
            candidates = [f"{clean_symbol}.TW", f"{clean_symbol}.TWO"]

        last_err = ""
        for candidate in candidates:
            # 對每個 candidate 最多重試 3 次
            for attempt in range(3):
                # 隨機等待避免被偵測，重試次數越多等越久
                base_sleep = 0.5 + attempt * 2
                time.sleep(random.uniform(base_sleep, base_sleep + 1.5))
                
                try:
                    ticker = yf.Ticker(candidate)
                    # 抓取資料
                    history = ticker.history(period="1y", interval="1d")
                    if history is not None and not history.empty:
                        history = history.dropna(subset=["Close"])
                        if not history.empty:
                            # 存入快取
                            self._save_to_cache(candidate, history)
                            return candidate, ticker, history
                except Exception as e:
                    err_msg = str(e)
                    last_err = err_msg
                    if "Too Many Requests" in err_msg:
                        # 遇到限流，增加等待時間後重試當前 candidate
                        time.sleep(3)
                        continue
                    else:
                        # 其他錯誤則跳過當前 candidate
                        break
            
            # 如果三次都失敗且不是其他錯誤，會繼續試下一個 candidate

        raise ValueError(f"無法獲取 {symbol} 的交易資料。原因: {last_err}")

    def _get_benchmark_candidates(self, symbol: str) -> List[Tuple[str, str]]:
        if symbol.endswith(".TWO"):
            return [("^TWOII", "櫃買指數"), ("^TWII", "加權指數")]
        if symbol.endswith(".TW"):
            return [("^TWII", "加權指數")]
        return []

    def _fetch_benchmark_history(self, symbol: str) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
        for benchmark_symbol, benchmark_name in self._get_benchmark_candidates(symbol):
            try:
                history = yf.Ticker(benchmark_symbol).history(period="6mo", interval="1d")
                history = history.dropna(subset=["Close"])
                if not history.empty:
                    return benchmark_name, history
            except Exception:
                continue
        return None, None

    def _fetch_official_rows(self, symbol: str) -> List[dict]:
        code = symbol.split(".")[0]
        is_tse = symbol.endswith(".TW")
        
        # 取得目前與過去六個月的日期，確保即使某幾個月 API 失敗也能有足夠的交易日計算 MA60
        now = datetime.now()
        months_to_fetch = [now]
        current_date = now
        for _ in range(6):
            current_date = current_date.replace(day=1) - timedelta(days=1)
            months_to_fetch.append(current_date)
        
        all_parsed_rows = []

        for date_obj in months_to_fetch:
            date_str_query = date_obj.strftime("%Y%m%d")
            for attempt in range(3):
                try:
                    if is_tse:
                        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str_query}&stockNo={code}"
                        payload = self._request_json(url)
                        if payload.get("stat") != "OK":
                            break
                        rows = payload.get("data", [])
                    else:
                        # TPEx 格式稍有不同
                        url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/stk_code_result.php?l=zh-tw&d={date_obj.strftime('%Y/%m')}&stk_code={code}"
                        payload = self._request_json(url)
                        rows = payload.get("aaData", [])

                    for row in rows:
                        try:
                            date_str = row[0]
                            year, month, day = date_str.split("/")
                            actual_date = datetime(int(year) + 1911, int(month), int(day))
                            close_idx = 6
                            volume_idx = 1
                            volume_multiplier = 1 if is_tse else 1000

                            all_parsed_rows.append(
                                {
                                    "date": pd.Timestamp(actual_date),
                                    "Open": float(row[3].replace(",", "")),
                                    "High": float(row[4].replace(",", "")),
                                    "Low": float(row[5].replace(",", "")),
                                    "Close": float(row[close_idx].replace(",", "")),
                                    "Volume": int(row[volume_idx].replace(",", "")) * volume_multiplier,
                                    "Dividends": 0.0,
                                    "Stock Splits": 0.0,
                                }
                            )
                        except (IndexError, ValueError, TypeError):
                            continue
                    break # Success, break the retry loop
                except Exception as e:
                    if attempt == 2:
                        print(f">>> 官方 API 請求失敗 ({date_str_query}): {e}")
                    else:
                        time.sleep(1.5 + random.uniform(0, 1))

        # 移除重複日期並排序
        unique_rows = {row["date"]: row for row in all_parsed_rows}
        return sorted(unique_rows.values(), key=lambda x: x["date"])

    def _merge_official_rows(self, history: pd.DataFrame, official_rows: List[dict]) -> pd.DataFrame:
        if history.empty or not official_rows:
            return history

        merged = history.copy()
        if not isinstance(merged.index, pd.DatetimeIndex):
            merged.index = pd.to_datetime(merged.index)

        if merged.index.tz is not None:
            history_dates = {ts.tz_localize(None).normalize() for ts in merged.index}
        else:
            history_dates = {ts.normalize() for ts in merged.index}

        last_history_date = max(history_dates)

        for row in official_rows:
            row_date = row["date"]
            normalized_row_date = row_date.normalize()
            index_value = (
                row_date.tz_localize(merged.index.tz)
                if merged.index.tz is not None
                else row_date
            )
            row_values = {key: value for key, value in row.items() if key != "date"}

            if normalized_row_date in history_dates:
                mask = merged.index.normalize() == index_value.normalize()
                # 取得原本的資料，進行「非空覆蓋」
                existing_row = merged.loc[mask].iloc[0]
                new_values = {}
                for key, val in row_values.items():
                    # 如果新資料有值且不為 0，或舊資料本身是 NaN，則更新
                    if pd.notna(val) and (val != 0 or pd.isna(existing_row.get(key))):
                        if key == "Volume" and pd.notna(existing_row.get(key)):
                            new_values[key] = max(val, existing_row.get(key))
                        elif key == "High" and pd.notna(existing_row.get(key)):
                            new_values[key] = max(val, existing_row.get(key))
                        elif key == "Low" and pd.notna(existing_row.get(key)):
                            new_values[key] = min(val, existing_row.get(key))
                        else:
                            new_values[key] = val
                    else:
                        new_values[key] = existing_row.get(key)
                
                merged.loc[mask, list(new_values.keys())] = list(new_values.values())
            elif normalized_row_date > last_history_date:
                merged = pd.concat([merged, pd.DataFrame([row_values], index=[index_value])])

        merged = merged.sort_index()
        return merged

    def _resolve_stock_name(self, symbol: str, ticker: yf.Ticker) -> str:
        clean_code = symbol.split(".")[0]
        
        # 1. 優先使用 twstock 內建字典取得標準中文名稱
        import twstock
        if clean_code in twstock.codes:
            return twstock.codes[clean_code].name

        if clean_code in self.mapping:
            return self.mapping[clean_code]

        raw_name = ticker.info.get("longName") or ticker.info.get("shortName") or symbol
        return (
            raw_name.replace("Limited", "")
            .replace("Corporation", "")
            .replace("Co., Ltd.", "")
            .strip()
        )

    def _fetch_twstock_realtime(self, symbol: str) -> Optional[dict]:
        """透過 twstock 抓取即時盤中資料 (零延遲)"""
        code = symbol.split(".")[0]
        try:
            # twstock.realtime.get 支援單一或多個代碼
            rt = twstock.realtime.get(code)
            if not rt or not rt.get('success'):
                return None
            
            data = rt.get('realtime')
            if not data:
                return None
                
            # 取得最新成交價 (如果尚未成交則用昨收/開盤?)
            # twstock 回傳格式: 'latest_trade_price'
            latest_price = data.get('latest_trade_price')
            
            def is_valid_price(p):
                try:
                    return p and p != '-' and float(p) > 0
                except (ValueError, TypeError):
                    return False
                    
            if not is_valid_price(latest_price):
                # 盤中若無成交或為市價單 (0.0000)，嘗試抓取買進價第一檔有效價格
                found = False
                for bid in data.get('best_bid_price', []):
                    if is_valid_price(bid):
                        latest_price = bid
                        found = True
                        break
                # 若無有效買進價，則嘗試抓取賣出價
                if not found:
                    for ask in data.get('best_ask_price', []):
                        if is_valid_price(ask):
                            latest_price = ask
                            break
            
            if not is_valid_price(latest_price):
                return None

            # 取得成交量 (當日累計)
            # 注意: twstock 的量能有時是以「張」為單位，需換算回「股」以與歷史數據同步
            accumulated_vol = data.get('accumulate_trade_volume')
            vol_shares = 0
            if accumulated_vol and accumulated_vol != '-':
                vol_val = int(accumulated_vol)
                # twstock 盤中 API 的 accumulate_trade_volume 固定以「張」為單位，一律乘以 1000 轉為「股」以與歷史數據同步
                vol_shares = vol_val * 1000

            # 日期處理
            info = rt.get('info', {})
            date_str = info.get('time')
            dt = pd.to_datetime(date_str) if date_str else pd.Timestamp.now().normalize()

            return {
                "date": dt,
                "Open": float(data.get('open', 0)),
                "High": float(data.get('high', 0)),
                "Low": float(data.get('low', 0)),
                "Close": float(latest_price),
                "Volume": vol_shares,
                "Dividends": 0.0,
                "Stock Splits": 0.0,
            }
        except Exception as e:
            print(f">>> twstock 即時抓取失敗: {e}")
            return None

    def _fetch_finmind_history(self, symbol: str) -> pd.DataFrame:
        code = symbol.split(".")[0]
        # 抓取過去一年的資料
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={code}&start_date={start_date}"
        
        try:
            payload = self._request_json(url)
            data = payload.get("data", [])
            if not data:
                return pd.DataFrame()
                
            rows = []
            for item in data:
                try:
                    rows.append({
                        "date": pd.Timestamp(item["date"]),
                        "Open": float(item["open"]),
                        "High": float(item["max"]),
                        "Low": float(item["min"]),
                        "Close": float(item["close"]),
                        "Volume": int(item["Trading_Volume"]),
                        "Dividends": 0.0,
                        "Stock Splits": 0.0,
                    })
                except (KeyError, ValueError, TypeError):
                    continue
            
            df = pd.DataFrame(rows)
            if not df.empty:
                df.set_index("date", inplace=True)
                df = df.sort_index()
            return df
        except Exception as e:
            print(f">>> FinMind API 請求錯誤: {e}")
            return pd.DataFrame()

    def fetch_data(self, symbol: Optional[str] = None) -> bool:
        if symbol:
            self.symbol = self._normalize_symbol(symbol)
        elif self.symbol:
            self.symbol = self._normalize_symbol(self.symbol)
        else:
            raise ValueError("請提供股票代碼。")

        # 1. 先嘗試從官方 API 抓取本月資料 (最穩定，不限流)
        official_history = pd.DataFrame()
        try:
            rows = self._fetch_official_rows(self.symbol)
            if rows:
                official_history = pd.DataFrame(rows)
                official_history.set_index("date", inplace=True)
        except Exception as e:
            print(f">>> 官方 API 抓取警告: {e}")

        # 2. 嘗試從快取或 yfinance 補足歷史資料 (用於均線計算)
        target_symbol = self.symbol
        yfinance_df = self._load_from_cache(self.symbol)
        ticker_obj = None

        if yfinance_df is None:
            try:
                # 隨機等待避免偵測
                time.sleep(random.uniform(0.5, 1.5))
                target_symbol, ticker_obj, yfinance_df = self._fetch_yfinance_history(self.symbol)
                self._save_to_cache(target_symbol, yfinance_df)
            except Exception as e:
                print(f">>> yfinance 抓取失敗 (可能是 Rate Limit): {e}")
                needs_finmind = False
                if official_history.empty or len(official_history) < 60:
                    needs_finmind = True
                elif not official_history.empty:
                    last_date = official_history.index[-1]
                    if last_date.tz is not None:
                        last_date = last_date.tz_localize(None)
                    if (pd.Timestamp.now() - last_date).days > 5:
                        needs_finmind = True
                        
                if needs_finmind:
                    print(">>> 嘗試使用 FinMind 作為最終備援...")
                    try:
                        finmind_df = self._fetch_finmind_history(self.symbol)
                        if not finmind_df.empty:
                            official_history = finmind_df
                    except Exception as finmind_e:
                        print(f">>> FinMind 抓取失敗: {finmind_e}")
                
                if official_history.empty:
                    raise ValueError(f"無法獲取 {self.symbol} 的資料。官方 API、Yahoo 與 FinMind 均失效。")
                yfinance_df = pd.DataFrame()

        # 3. 合併資料 (以 yfinance 為底，官方資料覆蓋)
        if not yfinance_df.empty:
            self.df = self._merge_official_rows(yfinance_df, official_history.reset_index().to_dict('records'))
            self.symbol = target_symbol
        else:
            self.df = official_history
            print(">>> 警告: 僅使用官方近期資料，長期指標可能不準確。")

        # 4. 盤中強化: 使用 twstock 抓取零延遲即時資料
        rt_data = self._fetch_twstock_realtime(self.symbol)
        if rt_data:
            # 將即時資料合併進入 df
            self.df = self._merge_official_rows(self.df, [rt_data])
            
            # 判斷是否為盤中 (09:00 - 13:35，考量最後一筆搓合)，需考慮時區 (UTC+8)
            from datetime import timezone, timedelta
            tw_tz = timezone(timedelta(hours=8))
            now = datetime.now(tw_tz)
            if now.weekday() < 5: # 週一至週五
                start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
                end_time = now.replace(hour=13, minute=30, second=0, microsecond=0)
                if start_time <= now <= end_time:
                    self.is_intraday = True
            # print(f">>> 已整合盤中即時數據: {rt_data['Close']} (Vol: {rt_data['Volume']})")

        if self.df.empty:
            raise ValueError("清理後無有效交易資料。")
            
        # 驗證資料連續性，防止因為歷史資料缺失導致 prev_row 抓到太舊的資料引發異常的漲跌幅
        if len(self.df) >= 2:
            last_date = self.df.index[-1]
            prev_date = self.df.index[-2]
            if (last_date - prev_date).days > 15:
                raise ValueError(f"歷史資料嚴重缺失 (缺少 {prev_date.strftime('%Y-%m-%d')} 至 {last_date.strftime('%Y-%m-%d')} 的資料)，請稍後再試。")

        # 4. 解析股票名稱
        try:
            if ticker_obj is None:
                ticker_obj = yf.Ticker(self.symbol)
            self.stock_name = self._resolve_stock_name(self.symbol, ticker_obj)
        except Exception:
            self.stock_name = self.mapping.get(self.symbol.split('.')[0], self.symbol)

        # 5. 大盤基準 (非必要，失敗不中斷)
        try:
            benchmark_name, benchmark_history = self._fetch_benchmark_history(self.symbol)
            self.benchmark_name = benchmark_name or "加權指數"
            self.benchmark_df = benchmark_history
        except Exception:
            pass

        return True


    def get_tick_size(self, price: float) -> float:
        if price < 10:
            return 0.01
        if price < 50:
            return 0.05
        if price < 100:
            return 0.1
        if price < 500:
            return 0.5
        if price < 1000:
            return 1.0
        return 5.0

    def round_to_tick(self, price: Optional[float]) -> Optional[float]:
        if price is None or pd.isna(price):
            return None
        tick = self.get_tick_size(float(price))
        return round(float(price) / tick) * tick
