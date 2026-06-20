# TradeOracle 自動化股票分析系統

TradeOracle 是一個基於 Python 的全自動化台股分析工具。系統能自動抓取歷史行情與籌碼數據，計算多維度技術指標（均線、RSI、KD、MACD、ADX/DI 等），並透過專家規則引擎進行即時判讀，提供具備操作建議、風險摘要與支撐觀察的分析報告。

本專案提供三種主要使用介面，滿足不同場景的看盤需求：**桌面圖形介面 (GUI)**、**終端機文字介面 (CLI)**，以及 **Line Bot 即時對話機器人**。

## 🌟 核心功能 (Key Features)

* **多重數據來源自動備援**：整合 `twstock` (盤中即時報價)、`yfinance` (歷史行情)、證交所/櫃買中心官方 API，以及 FinMind (備援)，確保資料的準確性與穩定性。
* **專家分析引擎**：
  * **趨勢與動能**：計算 SMA、RSI、KD、MACD。
  * **趨勢強度與風險**：使用 ADX/DI 判斷趨勢強度，利用 ATR (真實波動幅度) 衡量風險與設定動態停損。
  * **籌碼與量價分析**：判斷主力進場/出貨訊號、量價背離、突破與跌破狀態。
* **智慧快取機制 (Smart Cache)**：
  * 針對盤中與盤後設計不同的快取策略（如盤後快取自動延長至隔日開盤），並支援 Line Bot 的 Firestore 快取，大幅減少不必要的 API 請求與運算資源。
* **三合一表現層 (Presentation Layer)**：
  * **GUI 桌面看板**：基於 `tkinter` 開發，提供清晰的「行情摘要」、「決策重心」、「關鍵價位」與背景執行終端。
  * **CLI 終端儀表板**：基於 `Rich` 打造，在終端機中呈現高質感的彩色數據看板。
  * **Line Bot**：基於 `Flask` 與 `line-bot-sdk` 開發，支援高併發查詢，隨時隨地用手機掌握個股動態。
* **互動式圖表報告**：自動產生 `Plotly` 高品質技術圖表 (HTML 格式)，包含 K 線圖、均線、成交量與各項技術指標子圖。

## 🛠️ 系統架構 (Architecture)

* **Data Provider (數據接入層)**：負責抓取、清洗並整併來自多個 API 的盤中與歷史數據。
* **Analytics Engine (運算引擎層)**：利用 `pandas_ta` 計算技術指標，並套用專家規則進行狀態判定與多空訊號評估。
* **Presentation Layer (表現層)**：負責將分析結果透過不同介面呈現給使用者。

## 💻 技術棧 (Tech Stack)

* **核心語言**: Python 3.10+
* **數據處理與運算**: `pandas`, `numpy`, `pandas_ta`
* **金融數據 API**: `yfinance`, `twstock`, 證交所 API
* **視覺化與介面**:
  * `tkinter` (GUI)
  * `rich` (CLI)
  * `plotly` (互動式圖表)
  * `matplotlib` (Line Bot 靜態圖表生成)
* **Web 與後端 (Line Bot)**: `Flask`, `gunicorn`, `google-cloud-firestore`

## 🚀 安裝與執行 (Installation & Usage)

### 1. 安裝依賴套件

請先確保已安裝 Python 3.10 以上版本，然後執行以下指令安裝所需套件：

```bash
pip install -r requirements.txt
```

### 2. 初始化股票名稱對應表 (首次執行)

系統需要建立代碼與中文名稱的對應表，請先執行：

```bash
python update_stock_names.py
```

### 3. 啟動系統

你可以根據需求選擇不同的介面啟動：

* **桌面版 GUI (Desktop Dashboard)**
  ```bash
  python gui.py
  ```

* **終端機版 CLI (Command Line Interface)**
  ```bash
  python stock_expert.py
  ```

* **Line Bot 服務 (Web Server)**
  ```bash
  python line_bot_app.py
  ```
  *(註：需在 `.env` 中配置 `LINE_CHANNEL_SECRET` 與 `LINE_CHANNEL_ACCESS_TOKEN`)*

## ☁️ GCP 部署 (Deploying Line Bot to Cloud Run)

本專案支援將 Line Bot 部署至 Google Cloud Run，並搭配 Firestore 作為分析結果快取，以及 Cloud Storage 儲存技術分析圖表。

### 部署步驟

1. **環境準備**：
   * 安裝並初始化 [Google Cloud SDK (gcloud CLI)](https://cloud.google.com/sdk/docs/install)。
   * 確認您的 GCP 專案已啟用以下 API：Cloud Run, Firestore (原生模式), Cloud Storage, Secret Manager。
   * 將 LINE 金鑰存入 Secret Manager：
     ```bash
     echo "您的 Channel Secret" | gcloud secrets create LINE_CHANNEL_SECRET --data-file=-
     echo "您的 Access Token" | gcloud secrets create LINE_CHANNEL_ACCESS_TOKEN --data-file=-
     ```
   * 建立一個 Cloud Storage Bucket 作為圖表儲存空間，權限須設定為允許公開讀取 (allUsers)。

2. **設定部署腳本**：
   * 複製 `deploy_line_bot.bat.sample` 與 `update_url.bat.sample`，並將檔名結尾的 `.sample` 移除，還原成 `.bat` 執行檔。
   * 打開 [`deploy_line_bot.bat`](./deploy_line_bot.bat)，將 `REGION`, `PROJECT_ID`, `SERVICE_NAME` 與 `BUCKET_NAME` 替換為您的 GCP 設定。

3. **執行部署**：
   * 於專案根目錄下，在命令提示字元執行：
     ```bash
     deploy_line_bot.bat
     ```
   * 部署成功後，會獲得一組 Cloud Run 提供的 HTTPS 網址。
   * 請將此網址結尾加上 `/callback`，填入 LINE Developers Console 的 Webhook URL 並進行驗證。
   * （可選）將取得的正式網址透過執行 `update_url.bat` 腳本填入，這會自動幫您更新 Cloud Run 的環境變數，讓 Bot 知道自己的伺服器網址。

## 📂 專案結構簡介

* `data.py`: 核心資料抓取與處理模組。
* `signals.py`: 負責技術指標計算與專家規則判讀。
* `presentation.py`: 負責 CLI 畫面渲染與 Plotly 圖表生成。
* `gui.py`: 桌面版圖形使用者介面程式。
* `stock_expert.py`: CLI 版本主程式。
* `line_bot_app.py`: Line Bot 服務主程式。
* `update_stock_names.py`: 股票代碼與名稱更新腳本。
* `STOCK_EXPERT_SPEC.md`: 詳細的系統開發規格書。
* `GEMINI.md` / `HISTORY.md`: Agent 開發規範與修復歷史紀錄。

## 📝 授權與注意事項

* 本專案抓取之金融數據僅供參考與學術研究使用，不構成任何投資建議。
* 由於依賴多個外部 API，請注意抓取頻率，避免觸發 Rate Limit。
