import os
import math
from flask import Flask, request, jsonify
from flask_cors import CORS
from presentation import StockExpertSystem
from data import is_valid_symbol

app = Flask(__name__)
CORS(app) # Enable CORS for frontend

def handle_nan(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return val

@app.route('/api/analyze', methods=['GET'])
def analyze():
    symbol = request.args.get('symbol', '').strip()
    if not symbol:
        return jsonify({"success": False, "error": "Missing symbol parameter"}), 400
        
    if not is_valid_symbol(symbol):
        return jsonify({"success": False, "error": f"Invalid symbol: {symbol}"}), 400

    try:
        expert = StockExpertSystem(symbol)
        expert.fetch_data(symbol)
        expert.analyze()
        report_path = expert.export_plotly_report()
        
        snapshot = expert.build_snapshot()
        
        data = {
            "stock_name": snapshot.stock_name,
            "symbol": snapshot.symbol,
            "last_date": snapshot.last_date,
            "is_intraday": snapshot.is_intraday,
            "change": handle_nan(snapshot.change),
            "close": handle_nan(snapshot.close),
            "pct_change": handle_nan(snapshot.pct_change),
            "volume": handle_nan(snapshot.volume),
            "vma5": handle_nan(snapshot.vma5),
            "advice_text": snapshot.advice_text,
            "advice_color": snapshot.advice_color,
            "support": handle_nan(snapshot.support),
            "resistance": handle_nan(snapshot.resistance),
            "stop_loss": handle_nan(snapshot.stop_loss),
            "breakout_high_20": handle_nan(snapshot.breakout_high_20),
            "breakout_low_20": handle_nan(snapshot.breakout_low_20),
            "rsi14": handle_nan(snapshot.rsi14),
            "kd_k": handle_nan(snapshot.kd_k),
            "kd_d": handle_nan(snapshot.kd_d),
            "adx14": handle_nan(snapshot.adx14),
            "di_plus": handle_nan(snapshot.di_plus),
            "di_minus": handle_nan(snapshot.di_minus),
            "trend_status": snapshot.trend_status,
            "relative_strength_20d": handle_nan(snapshot.relative_strength_20d),
            "benchmark_name": snapshot.benchmark_name,
            "force_alert": snapshot.force_alert,
            "divergence": snapshot.divergence,
            "atr14": handle_nan(snapshot.atr14),
            "breakout_status": snapshot.breakout_status,
            "risk_note": snapshot.risk_note,
            "report_url": f"http://127.0.0.1:5000/reports/{os.path.basename(report_path)}" if report_path else None
        }
        
        return jsonify({"success": True, "data": data})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/reports/<path:filename>')
def serve_report(filename):
    from flask import send_from_directory
    report_dir = os.path.join(os.getcwd(), "reports")
    return send_from_directory(report_dir, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)
