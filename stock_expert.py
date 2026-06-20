import argparse

import tkinter as tk

from gui import StockExpertGUI
from presentation import StockExpertSystem


def main() -> None:
    parser = argparse.ArgumentParser(description="StockExpert-Py")
    parser.add_argument("symbol", nargs="?", help="股票代碼 (選填，不填則啟動 GUI)")
    parser.add_argument("--no-chart", action="store_true", help="僅輸出文字分析")
    parser.add_argument("--gui", action="store_true", help="強制啟動 GUI 模式")
    args = parser.parse_args()

    if args.gui or not args.symbol:
        root = tk.Tk()
        StockExpertGUI(root)
        root.mainloop()
        return

    expert = StockExpertSystem(args.symbol)
    from data import is_valid_symbol
    if not is_valid_symbol(args.symbol):
        expert.console.print(f"[bold red]錯誤:[/] 您輸入的代號「{args.symbol}」無效，請確認後再試。")
        return

    with expert.console.status(f"[bold green]分析中: {args.symbol}..."):
        try:
            expert.fetch_data()
            expert.analyze()
            expert.show_cli_dashboard()
            if not args.no_chart:
                path = expert.export_plotly_report()
                expert.console.print(f"\n[bold green]報告已存於資料夾:[/] {path}")
        except Exception as exc:
            expert.console.print(f"[bold red]錯誤:[/] {exc}")


if __name__ == "__main__":
    main()
