import math
import os
import threading
import webbrowser
from datetime import datetime
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk

from presentation import StockExpertSystem


class StockExpertGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("StockExpert-Py 專家分析系統 (Dashboard)")
        self.root.geometry("1000x900")
        self.expert = StockExpertSystem(is_gui=True)
        self._setup_styles()
        self._setup_ui()

    def _setup_styles(self) -> None:
        self.style = ttk.Style()
        self.style.configure("Header.TLabel", font=("Microsoft JhengHei", 18, "bold"))
        self.style.configure("Price.TLabel", font=("Consolas", 28, "bold"))
        self.style.configure("Treeview", font=("Microsoft JhengHei", 12), rowheight=30)
        self.style.configure("Treeview.Heading", font=("Microsoft JhengHei", 12, "bold"))

    def _setup_ui(self) -> None:
        control_frame = ttk.Frame(self.root, padding="15")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="股票代碼:").pack(side=tk.LEFT)
        self.symbol_entry = ttk.Entry(control_frame, font=("Consolas", 12))
        self.symbol_entry.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        self.symbol_entry.bind("<Return>", lambda _event: self.run_analysis())

        self.enable_chart = tk.BooleanVar(value=True)
        self.chk_chart = ttk.Checkbutton(control_frame, text="產生圖表", variable=self.enable_chart)
        self.chk_chart.pack(side=tk.LEFT, padx=5)

        self.btn_run = ttk.Button(control_frame, text="執行分析", command=self.run_analysis)
        self.btn_run.pack(side=tk.LEFT, padx=5)

        self.btn_chart = ttk.Button(
            control_frame,
            text="開啟互動報告",
            command=self.open_report,
            state=tk.DISABLED,
        )
        self.btn_chart.pack(side=tk.LEFT, padx=5)

        dash_upper = ttk.Frame(self.root, padding="10")
        dash_upper.pack(fill=tk.X)

        self.card_market = ttk.LabelFrame(dash_upper, text=" 行情摘要 ", padding="15")
        self.card_market.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.lbl_name = ttk.Label(self.card_market, text="---", style="Header.TLabel")
        self.lbl_name.pack(anchor=tk.W)
        self.lbl_price = ttk.Label(self.card_market, text="0.00", style="Price.TLabel")
        self.lbl_price.pack(anchor=tk.W, pady=5)
        self.lbl_change = ttk.Label(
            self.card_market,
            text="0.00 (0.00%)",
            font=("Consolas", 14, "bold"),
        )
        self.lbl_change.pack(anchor=tk.W)
        self.lbl_date = ttk.Label(
            self.card_market,
            text="最後交易日: ---",
            font=("Consolas", 11),
            foreground="#666666",
        )
        self.lbl_date.pack(anchor=tk.W, pady=(6, 0))
        self.lbl_volume = ttk.Label(
            self.card_market,
            text="成交量: --- | 5日均量: ---",
            font=("Microsoft JhengHei", 11),
            foreground="#666666",
        )
        self.lbl_volume.pack(anchor=tk.W, pady=(4, 0))

        self.card_verdict = ttk.LabelFrame(dash_upper, text=" 專家決策 ", padding="15")
        self.card_verdict.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.advice_box = tk.Label(
            self.card_verdict,
            text="等待數據...",
            font=("Microsoft JhengHei", 16, "bold"),
            bg="#2a2a2a",
            fg="white",
            padx=20,
            pady=15,
            relief=tk.RIDGE,
            wraplength=350,
        )
        self.advice_box.pack(fill=tk.BOTH, expand=True)
        self.lbl_focus = ttk.Label(
            self.card_verdict,
            text="",
            font=("Microsoft JhengHei", 14, "bold"),
            foreground="#005588",
        )
        self.lbl_focus.pack(pady=(5, 0), anchor=tk.W)

        dash_middle = ttk.Frame(self.root, padding="10")
        dash_middle.pack(fill=tk.X)

        self.card_metrics = ttk.LabelFrame(dash_middle, text=" 技術指標明細 ", padding="10")
        self.card_metrics.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.tree = ttk.Treeview(
            self.card_metrics,
            columns=("metric", "value", "status"),
            show="headings",
            height=7,
        )
        self.tree.heading("metric", text="指標名稱")
        self.tree.heading("value", text="當前數值")
        self.tree.heading("status", text="狀態判定")
        self.tree.column("metric", width=120)
        self.tree.pack(fill=tk.X)
        self.tree.tag_configure("red", foreground="#cc0000")
        self.tree.tag_configure("green", foreground="#007700")
        self.tree.tag_configure("yellow", foreground="#886600")
        self.tree.tag_configure("cyan", foreground="#005588")

        self.card_levels = ttk.LabelFrame(dash_middle, text=" 關鍵價位矩陣 ", padding="10")
        self.card_levels.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.lbl_levels = ttk.Label(
            self.card_levels,
            text="壓力位: ---\n支撐位: ---\n停損位: ---\n20日高/低: --- / ---",
            font=("Consolas", 12),
            justify=tk.LEFT,
        )
        self.lbl_levels.pack(pady=10)

        self.card_risk = ttk.LabelFrame(self.root, text=" 風險與突破摘要 ", padding="10")
        self.card_risk.pack(fill=tk.X, padx=15, pady=(0, 10))
        self.lbl_risk = ttk.Label(
            self.card_risk,
            text="ATR14: --- | 20日狀態: --- | 風險: ---",
            font=("Microsoft JhengHei", 11),
            justify=tk.LEFT,
        )
        self.lbl_risk.pack(anchor=tk.W)

        self.card_log = ttk.LabelFrame(self.root, text=" 執行日誌 (Execution Log) ", padding="5")
        self.card_log.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        self.console_text = tk.Text(
            self.card_log,
            bg="#0c0c0c",
            fg="#f8f8f2",
            font=("Consolas", 11),
            wrap=tk.NONE,
            insertbackground="white",
            padx=10,
            pady=10,
        )
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.console_text.tag_config("31", foreground="#ff5555")
        self.console_text.tag_config("bold", font=("Consolas", 11, "bold"))

        scrollbar_y = ttk.Scrollbar(self.card_log, orient=tk.VERTICAL, command=self.console_text.yview)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_text.configure(yscrollcommand=scrollbar_y.set)
        self.console_text.insert(tk.END, ">>> 系統就緒。請輸入代碼執行分析。")
        self.console_text.config(state=tk.DISABLED)

    def _log(self, message: str, tag: Optional[str] = None) -> None:
        self.console_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.console_text.see(tk.END)
        self.console_text.config(state=tk.DISABLED)

    def run_analysis(self) -> None:
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            return

        from data import is_valid_symbol
        if not is_valid_symbol(symbol):
            messagebox.showerror("錯誤", f"您輸入的代號「{symbol}」無效，請確認後再試。")
            return

        generate_chart = bool(self.enable_chart.get())
        self.btn_run.config(state=tk.DISABLED)
        self.btn_chart.config(state=tk.DISABLED)
        self.console_text.config(state=tk.NORMAL)
        self.console_text.delete(1.0, tk.END)
        self.console_text.config(state=tk.DISABLED)
        self._log(f">>> 開始分析股票: {symbol}", "bold")
        self._log("正在連線至市場資料源...")
        threading.Thread(
            target=self._worker,
            args=(symbol, generate_chart),
            daemon=True,
        ).start()

    def _worker(self, symbol: str, generate_chart: bool) -> None:
        try:
            self.expert.fetch_data(symbol)
            self.root.after(0, self._log, "數據抓取成功，正在計算技術指標...")
            self.expert.analyze()

            report_path = None
            if generate_chart:
                self.root.after(0, self._log, "指標運算完成，正在產出視覺化報告...")
                report_path = self.expert.export_plotly_report()
            else:
                self.root.after(0, self._log, "指標運算完成 (跳過圖表產生)。")

            self.root.after(0, self._update_ui, report_path)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    def _show_error(self, message: str) -> None:
        self._log(f"[錯誤] {message}", "31")
        self.btn_run.config(state=tk.NORMAL)
        messagebox.showerror("錯誤", message)

    def _update_ui(self, report_path: Optional[str]) -> None:
        snapshot = self.expert.build_snapshot()

        self.lbl_name.config(text=f"{snapshot.stock_name} ({snapshot.symbol})")
        
        # 格式化日期為 YYYY/MM/DD
        display_date = snapshot.last_date.replace("-", "/")
        self.lbl_date.config(text=f"最後交易日: {display_date}")
        
        # 盤中標籤動態切換
        price_label = "最新價" if snapshot.is_intraday else "收盤價"
        
        change_color = "#d20000" if snapshot.change > 0 else "#008800"
        self.lbl_price.config(text=f"{snapshot.close:.2f} ({price_label})")
        self.lbl_change.config(
            text=f"{'▲' if snapshot.change > 0 else '▼'} {abs(snapshot.change):.2f} ({snapshot.pct_change:+.2f}%)",
            foreground=change_color,
        )
        volume_text = (
            f"成交量: {snapshot.volume/1000:,.0f} 張 | 5日均量: {snapshot.vma5/1000:,.0f} 張"
            if not math.isnan(snapshot.vma5)
            else f"成交量: {snapshot.volume/1000:,.0f} 張 | 5日均量: ---"
        )
        self.lbl_volume.config(text=volume_text)

        bg_map = {"red": "#442a2a", "orange": "#443b2a", "blue": "#2a2d44", "gray": "#2a2a2a"}
        fg_map = {"red": "#ff5555", "orange": "#ffb86c", "blue": "#8be9fd", "gray": "#bbbbbb"}
        self.advice_box.config(
            text=snapshot.advice_text,
            bg=bg_map.get(snapshot.advice_color, "#2a2a2a"),
            fg=fg_map.get(snapshot.advice_color, "white"),
        )
        self.lbl_focus.config(text=f"支撐觀察: {self.expert._format_level(snapshot.support)}")

        for item in self.tree.get_children():
            self.tree.delete(item)

        rsi_status = "中性"
        rsi_tag = "cyan"
        if snapshot.rsi14 is not None:
            if snapshot.rsi14 > 70:
                rsi_status = "超買"
                rsi_tag = "red"
            elif snapshot.rsi14 < 30:
                rsi_status = "超賣"
                rsi_tag = "green"
        self.tree.insert(
            "",
            "end",
            values=("RSI (14)", "---" if snapshot.rsi14 is None else f"{snapshot.rsi14:.1f}", rsi_status),
            tags=(rsi_tag,),
        )

        kd_value = "---/---"
        kd_status = "資料不足"
        kd_tag = "cyan"
        if snapshot.kd_k is not None and snapshot.kd_d is not None:
            kd_value = f"{snapshot.kd_k:.1f}/{snapshot.kd_d:.1f}"
            kd_status = "金叉" if snapshot.kd_k > snapshot.kd_d else "死叉"
            kd_tag = "red" if snapshot.kd_k > snapshot.kd_d else "green"
        self.tree.insert("", "end", values=("K/D 指標", kd_value, kd_status), tags=(kd_tag,))

        adx_value = "---"
        adx_status = "資料不足"
        adx_tag = "cyan"
        if snapshot.adx14 is not None and snapshot.di_plus is not None and snapshot.di_minus is not None:
            adx_value = f"{snapshot.adx14:.2f} / +DI {snapshot.di_plus:.2f} / -DI {snapshot.di_minus:.2f}"
            if snapshot.adx14 >= 25:
                adx_status = "趨勢成立"
                adx_tag = "red" if snapshot.di_plus > snapshot.di_minus else "green"
            elif snapshot.adx14 < 20:
                adx_status = "盤整震盪"
                adx_tag = "yellow"
            else:
                adx_status = "趨勢醞釀"
        self.tree.insert("", "end", values=("ADX / DI", adx_value, adx_status), tags=(adx_tag,))

        trend_tag = "cyan"
        if snapshot.trend_status == "多頭強勢":
            trend_tag = "red"
        elif snapshot.trend_status == "空頭強勢":
            trend_tag = "green"
        elif snapshot.trend_status == "空頭反彈":
            trend_tag = "yellow"

        self.tree.insert(
            "",
            "end",
            values=("均線排列", "SMA 5/20/60", snapshot.trend_status),
            tags=(trend_tag,),
        )

        rs_value = "---"
        rs_status = "資料不足"
        rs_tag = "cyan"
        if snapshot.relative_strength_20d is not None:
            rs_value = f"{snapshot.relative_strength_20d * 100:+.2f}%"
            if snapshot.relative_strength_20d > 0:
                rs_status = f"強於{snapshot.benchmark_name}"
                rs_tag = "red"
            elif snapshot.relative_strength_20d < 0:
                rs_status = f"弱於{snapshot.benchmark_name}"
                rs_tag = "green"
            else:
                rs_status = "與大盤同步"
        self.tree.insert("", "end", values=(f"相對{snapshot.benchmark_name}", rs_value, rs_status), tags=(rs_tag,))

        force_tag = "red" if ("進場" in snapshot.force_alert[0] or "爆量" in snapshot.force_alert[0]) else "green" if "出貨" in snapshot.force_alert[0] else "cyan"
        self.tree.insert(
            "",
            "end",
            values=("主力警示", snapshot.force_alert[0], "警示" if "主力" in snapshot.force_alert[0] else "正常"),
            tags=(force_tag,),
        )

        div_tag = "yellow" if "背離" in snapshot.divergence[0] else "cyan"
        self.tree.insert(
            "",
            "end",
            values=("量價分析", snapshot.divergence[0], "背離" if "背離" in snapshot.divergence[0] else "同步"),
            tags=(div_tag,),
        )

        self.lbl_levels.config(
            text=(
                f"壓力位: {self.expert._format_level(snapshot.resistance)}\n"
                f"支撐位: {self.expert._format_level(snapshot.support)}\n"
                f"停損位: {self.expert._format_level(snapshot.stop_loss)}\n"
                f"20日高/低: {self.expert._format_level(snapshot.breakout_high_20)} / {self.expert._format_level(snapshot.breakout_low_20)}"
            )
        )
        self.lbl_risk.config(
            text=(
                f"ATR14: {snapshot.atr14:.2f} | " if snapshot.atr14 is not None else "ATR14: --- | "
            ) + f"20日狀態: {snapshot.breakout_status} | 風險: {snapshot.risk_note}"
        )

        self._log("分析任務成功結束。")
        if report_path:
            self._log("報告已存至 reports 資料夾。")
            self.btn_chart.config(state=tk.NORMAL)
        else:
            self._log("圖表功能已停用。")
            self.btn_chart.config(state=tk.DISABLED)

        self.btn_run.config(state=tk.NORMAL)

    def open_report(self) -> None:
        if self.expert.report_path:
            webbrowser.open(f"file:///{os.path.abspath(self.expert.report_path)}")
