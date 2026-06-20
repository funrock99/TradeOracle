import os
import time
import threading
import logging
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, ImageMessage, PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from dotenv import load_dotenv
from google.cloud import firestore, storage
from datetime import datetime, timedelta, timezone

from presentation import StockExpertSystem

load_dotenv()
app = Flask(__name__)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = app.logger

# 全域 Semaphore 限制同時處理重型任務的數量為 5
analysis_semaphore = threading.Semaphore(5)

# 取得環境變數
project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')

# 初始化 GCP 客戶端
db = firestore.Client(project=project_id, database='stock-linebot')
storage_client = storage.Client(project=project_id)

# Line Bot 設定
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
server_url = os.getenv('SERVER_URL', '').rstrip('/')

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

def upload_to_gcs(local_path):
    """上傳圖片到 GCS 並回傳公開網址"""
    if not BUCKET_NAME:
        logger.error("錯誤: 未設定 GCS_BUCKET_NAME")
        return None
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = f"charts/{os.path.basename(local_path)}"
        blob = bucket.blob(blob_name)
        
        # 上傳檔案 (注意: 這裡不設定 content_type，讓 GCS 自動判斷)
        blob.upload_from_filename(local_path)
        
        # --- 核心修正：移除 blob.make_public() ---
        # 因為儲存桶已設定 allUsers，這裡不需要也不允許呼叫 make_public
        
        # 產生 GCS 標準公開網址
        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
        logger.info(f"圖片上傳成功: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"GCS 上傳過程中發生錯誤: {e}")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    if not signature:
        abort(400)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        logger.error(f"Webhook Handler Error: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    symbol_input = event.message.text.strip().upper()
    logger.info(f"收到查詢請求: {symbol_input}")
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 0. 本地端快速檢核 (阻擋無效代號)
        from data import is_valid_symbol
        if not is_valid_symbol(symbol_input):
            logger.warning(f"阻擋無效代號: {symbol_input}")
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token, 
                    messages=[TextMessage(text=f"分析失敗: 您輸入的代號「{symbol_input}」無效，請確認後再試。")]
                )
            )
            return
            

        # 1. 檢查 Firestore 快取
        try:
            cache_ref = db.collection('analysis_cache').document(symbol_input)
            cache = cache_ref.get()
            if cache.exists:
                data = cache.to_dict()
                from data import is_cache_valid
                if is_cache_valid(data['updated_at']):
                    logger.info(f">>> 使用 Firestore 快取: {symbol_input}")
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[
                                TextMessage(text=data['report_text']),
                                ImageMessage(original_content_url=data['chart_url'], preview_image_url=data['chart_url'])
                            ]
                        )
                    )
                    return
        except Exception as fe:
            logger.error(f"Firestore 讀取失敗: {fe}")

        # 2. 執行分析
        try:
            expert = StockExpertSystem(symbol_input)
            
            logger.info(f"等待進入佇列: {symbol_input}")
            with analysis_semaphore:
                logger.info(f"開始執行耗時運算: {symbol_input}")
                expert.fetch_data()
                expert.analyze()
            
            report_text = expert.get_line_report()
            chart_local_path = expert.export_line_chart()
            
            # 3. 上傳圖片 (檔名維持純資料日期)
            chart_cloud_url = upload_to_gcs(chart_local_path)
            
            # 4. 組合回覆
            messages = [TextMessage(text=report_text)]
            if chart_cloud_url:
                # 在 URL 後方加入時間戳作為 Cache Buster (解決 Line 快取問題，不影響 GCS 檔名)
                cache_buster_url = f"{chart_cloud_url}?v={int(time.time())}"
                messages.append(ImageMessage(original_content_url=cache_buster_url, preview_image_url=cache_buster_url))
                
                # 存入快取
                try:
                    cache_ref.set({
                        'report_text': report_text,
                        'chart_url': chart_cloud_url, # 存入 Firestore 時維持原始 URL
                        'updated_at': firestore.SERVER_TIMESTAMP,
                        'stock_name': expert.stock_name
                    })
                    logger.info(f"成功寫入 Firestore 快取: {symbol_input}")
                except Exception as cache_e:
                    logger.error(f"寫入 Firestore 快取失敗: {cache_e}")
            else:
                logger.warning("未能產生圖片網址，跳過快取寫入，僅回傳文字報告")
            
            try:
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
            except Exception as reply_e:
                logger.warning(f"Reply message 失敗 (可能超時): {reply_e}，改用 Push Message")
                line_bot_api.push_message(PushMessageRequest(to=event.source.user_id, messages=messages))
            
            # 紀錄 Log
            try:
                db.collection('analysis_logs').add({
                    'user_id': event.source.user_id,
                    'symbol': expert.symbol,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
            except Exception: pass

        except Exception as e:
            logger.error(f"分析失敗: {e}")
            error_messages = [TextMessage(text=f"分析失敗: {str(e)}")]
            try:
                line_bot_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=error_messages)
                )
            except Exception as inner_e:
                logger.warning(f"Reply 失敗: {inner_e}，改用 Push 傳送錯誤訊息")
                line_bot_api.push_message(PushMessageRequest(to=event.source.user_id, messages=error_messages))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
