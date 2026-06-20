# 使用官方 Python 3.12 輕量版作為基底
FROM python:3.12-slim


# 設定工作目錄
WORKDIR /app

# 安裝系統依賴 (含中文字型支援)
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 複製需求檔案並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 建立報告資料夾
RUN mkdir -p reports

# 設定環境變數 (Flask 埠號)
ENV PORT 8080

# 使用 gunicorn 啟動應用程式
# 注意: line_bot_app:app 對應檔案名稱與 Flask 變數名稱
CMD exec gunicorn --bind :$PORT --workers 1 --threads 32 --timeout 0 line_bot_app:app
