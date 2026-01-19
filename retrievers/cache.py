# retrievers/cache.py（純 print(f"...") 版 + 自動 STOCK_MAP 同步 + Thread-safe）
import time
import threading
import requests
from typing import Dict, Any, List, Optional
from config import FINMIND_API_KEY
from retrievers.stocks import fetch_price_finmind
from retrievers.news import fetch_news_finmind

# === FinMind 全域快取（股票名/代號表） ===
FINMIND_CACHE = {"data": None, "last_update": 0}
FINMIND_CACHE_TTL = 604800  # 7 天
_AUTO_REFRESH_STARTED = False
STOCK_MAP: Dict[str, str] = {}

PRICE_CACHE: Dict[str, Dict[str, Any]] = {}
NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
PRICE_CACHE_TTL = 120       # 2 分鐘
NEWS_CACHE_TTL = 86400      # 1 天

LOCK = threading.Lock()  # 🔒 避免多執行緒競態


# ---------------------------------------------------------
# FinMind 全域資料（股票清單）快取
# ---------------------------------------------------------
def get_finmind_data():
    """每週自動更新一次 TaiwanStockInfo 並同步更新 STOCK_MAP"""
    now = time.time()
    with LOCK:
        if not FINMIND_CACHE["data"] or now - FINMIND_CACHE["last_update"] > FINMIND_CACHE_TTL:
            print("[CACHE/FinMind] ⏳ 快取過期，重新抓取 TaiwanStockInfo...")
            try:
                url = "https://api.finmindtrade.com/api/v4/data"
                params = {"dataset": "TaiwanStockInfo"}
                headers = {"Authorization": f"Bearer {FINMIND_API_KEY}"}
                res = requests.get(url, params=params, headers=headers, timeout=15)
                res.raise_for_status()
                data = res.json().get("data", [])
                FINMIND_CACHE["data"] = data
                FINMIND_CACHE["last_update"] = now

                # ✅ 更新 STOCK_MAP
                STOCK_MAP.clear()
                for item in data:
                    name = (item.get("stock_name") or "").strip()
                    code = (item.get("stock_id") or "").strip()
                    if name and code:
                        STOCK_MAP[name.upper()] = code
                        STOCK_MAP[code] = code

                print(f"[CACHE/FinMind] ✅ 更新成功：FinMind 共 {len(data)} 筆 → 有效股票 {len(STOCK_MAP)//2} 檔。")
                print(f"[CACHE/FinMind] ✅ STOCK_MAP 更新完成（來源：FinMind API），共 {len(STOCK_MAP)//2} 檔。")

            except Exception as e:
                print(f"[CACHE/FinMind] ⚠️ 更新失敗：{e}")
                print("[CACHE/FinMind] ⚠️ 使用舊的快取資料以維持服務。")
        else:
            print("[CACHE/FinMind] ✅ 使用快取中的 TaiwanStockInfo（未過期）")
    return FINMIND_CACHE["data"]


# ---------------------------------------------------------
# 背景自動刷新
# ---------------------------------------------------------
def start_finmind_auto_refresh():
    """背景執行緒：每週自動刷新 FinMind 全快取"""
    global _AUTO_REFRESH_STARTED
    if _AUTO_REFRESH_STARTED:
        print("[CACHE/FinMind] ⚙️ 背景更新執行緒已啟動，略過重複。")
        return
    _AUTO_REFRESH_STARTED = True

    def loop():
        while True:
            print("\n[CACHE/FinMind] 🔁 背景刷新中...")
            get_finmind_data()
            load_stock_map_from_cache()
            print("[CACHE/FinMind] 🌱 背景刷新完成（FinMind + STOCK_MAP 已同步）\n")
            time.sleep(FINMIND_CACHE_TTL)
            # 🔁 通知 RAG 模組重新載入股票代號
            try:
                from rag import refresh_stock_map
                refresh_stock_map()
            except Exception as e:
                print(f"[CACHE/FinMind] ⚠️ 無法通知 RAG 更新：{e}")

    threading.Thread(target=loop, daemon=True).start()
    print("[CACHE/FinMind] 🚀 已啟動自動更新執行緒（每週刷新一次）")


# ---------------------------------------------------------
# 股票代號映射表
# ---------------------------------------------------------
def load_stock_map_from_cache() -> Dict[str, str]:
    """由 FinMind 全域快取建立 {名稱→代號, 代號→代號} 的映射表"""
    data = FINMIND_CACHE.get("data", [])
    if not data:
        print("[CACHE/FinMind] ❌ 無法載入股票清單（資料為空）。")
        return {}
    stock_map: Dict[str, str] = {}
    for item in data:
        name = (item.get("stock_name") or "").strip()
        code = (item.get("stock_id") or "").strip()
        if name and code:
            stock_map[name.upper()] = code
            stock_map[code] = code
    print(f"[CACHE/FinMind] ✅ STOCK_MAP 更新完成（來源：快取資料），共 {len(stock_map)//2} 檔。")
    return stock_map


# ---------------------------------------------------------
# 股價快取層
# ---------------------------------------------------------
def get_price_with_cache(ticker: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    if ticker in PRICE_CACHE and now - PRICE_CACHE[ticker]["time"] < PRICE_CACHE_TTL:
        print(f"[CACHE/Price] ✅ 使用快取股價 → {ticker}")
        return PRICE_CACHE[ticker]["data"]

    price = fetch_price_finmind(ticker, FINMIND_API_KEY)
    if price:
        PRICE_CACHE[ticker] = {"data": price, "time": now}
        print(f"[CACHE/Price] ✅ 股價更新完成 → {ticker}：{price['price']} ({price['pct']}%)")
    else:
        print(f"[CACHE/Price] ⚠️ 抓取 {ticker} 失敗或無資料。")
    return price


# ---------------------------------------------------------
# 新聞快取層
# ---------------------------------------------------------
def get_news_with_cache(ticker: str, company_name: Optional[str]) -> List[Dict[str, Any]]:
    now = time.time()
    if ticker in NEWS_CACHE and now - NEWS_CACHE[ticker]["time"] < NEWS_CACHE_TTL:
        print(f"[CACHE/News] ✅ 使用FinMind快取新聞 → {ticker}")
        return NEWS_CACHE[ticker]["data"]

    print(f"[CACHE/News] ⏳ 從 FinMind 抓取新聞 → {ticker}")
    news = fetch_news_finmind(ticker, FINMIND_API_KEY, company_name=company_name)
    if news:
        NEWS_CACHE[ticker] = {"data": news, "time": now}
        print(f"[CACHE/News] ✅ FinMind快取新聞更新完成 → {ticker}，共 {len(news)} 則。\n")
    else:
        NEWS_CACHE[ticker] = {"data": news, "time": now}
        print(f"[CACHE/News] ⚠️ 抓取 {ticker} 無新聞。")
    return news or []


# ---------------------------------------------------------
# 啟動時執行初始化
# ---------------------------------------------------------
get_finmind_data()
start_finmind_auto_refresh()
