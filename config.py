import os
from dotenv import load_dotenv

# 載入 .env 檔案中的環境變數
load_dotenv()

# --- 必要金鑰 (程式沒有這些就無法運行) ---
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FINMIND_API_KEY = os.getenv("FINMIND_API_KEY")

# --- 可選金鑰 (如果沒有，程式仍可透過備案運行) ---
#NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
#ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
#FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# 檢查「必要」金鑰是否存在，如果缺少任何一個，就拋出錯誤
if not all([LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OPENAI_API_KEY]):
    raise ValueError("警告：缺少 LINE 或 OpenAI 的 API 金鑰，請檢查你的 .env 檔案。")

# (可選) 增加時區設定，方便未來使用
TZ = "Asia/Taipei"