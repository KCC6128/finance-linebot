# retrievers/news.py（含詳細 LOG 版）
import requests
import feedparser
from datetime import datetime, timedelta


# ---------------------------------------------------------
# FinMind 新聞抓取
# ---------------------------------------------------------
def fetch_news_finmind(symbol_id: str, api_key: str, company_name: str = None):
    """
    使用 FinMind API 的 TaiwanStockNews 資料集獲取新聞。
    ✅ 加入標題過濾：必須包含公司名稱或代號。
    ✅ 若 symbol_id 查不到，再嘗試 company_name。
    """
    print(f"[NEWS/FinMind] 📰 開始抓取 FinMind 新聞 → 股票代號：{symbol_id}，公司名稱：{company_name}")

    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    def get_data(data_id: str):
        params = {
            'dataset': 'TaiwanStockNews',
            'data_id': data_id,
            'start_date': start_date,
            'token': api_key,
        }
        try:
            print(f"[NEWS/FinMind] 🔍 查詢 data_id = {data_id}")
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json().get('data', [])
            print(f"[NEWS/FinMind] ✅ API 回傳 {len(data)} 筆資料。")
            return data
        except Exception as e:
            print(f"[NEWS/FinMind] ⚠️ API 抓取 {data_id} 失敗：{e}")
            return []

    # Step 1️⃣：嘗試用股票代號查詢
    data = get_data(symbol_id)

    # Step 2️⃣：若代號沒結果、且公司名稱可用，再嘗試用名稱查
    if not data and company_name:
        print(f"[NEWS/FinMind] ⚠️ 無 {symbol_id} 資料，改用公司名稱 '{company_name}' 查詢...")
        data = get_data(company_name)

    # Step 3️⃣：若仍無資料，回傳空
    if not data:
        print(f"[NEWS/FinMind] ❌ 找不到 {symbol_id} 或 {company_name} 的新聞資料。")
        return []

    # Step 4️⃣：篩選新聞（標題須包含公司名或代號）
    out = []
    for news_item in data:
        title = news_item.get("title", "")
        if not title:
            continue
        if company_name and (company_name not in title and symbol_id not in title):
            continue
        out.append({
            "title": title,
            "source": news_item.get("source", ""),
            "publishedAt": news_item.get("date", ""),
            "url": news_item.get("link", "")
        })

    if not out:
        print("[NEWS/FinMind] ⚠️ FinMind 有資料，但標題未包含公司名或代號。")
        return []

    print(f"[NEWS/FinMind] ✅ 篩選後保留 {min(len(out), 8)} 則新聞。")
    for i, n in enumerate(out[:8]):
        print(f"   [{i+1}] {n['title']} | {n['source']}")

    print("[NEWS/FinMind] 🏁 FinMind 新聞抓取完成。\n")
    return out[:8]


# ---------------------------------------------------------
# Google News RSS 抓取
# ---------------------------------------------------------
def fetch_news_rss(company_name: str, symbol_id: str = None, hl="zh-TW"):
    """
    使用 Google News RSS feed 檢索新聞。
    ✅ 搜尋關鍵字：公司名稱 + 股票代號，確保更準確。
    """
    print(f"[NEWS/RSS] 🌐 開始抓取 Google News RSS → 關鍵字: '{company_name}', 代號: {symbol_id}")

    encoded_query = requests.utils.quote(f"{company_name} {symbol_id}" if symbol_id else company_name)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl=TW&ceid=TW:zh-Hant"

    try:
        print(f"[NEWS/RSS] 🔗 RSS URL: {url}")

        feed = feedparser.parse(url)

        if not hasattr(feed, "entries"):
            print("[NEWS/RSS] ⚠️ RSS 結果異常（無 entries 欄位）")
            return []

        out = []
        for e in feed.entries[:8]:
            out.append({
                "title": e.title,
                "source": getattr(e, "source", {}).get("title", ""),
                "publishedAt": getattr(e, "published", ""),
                "url": e.link
            })

        if not out:
            print(f"[NEWS/RSS] ❌ 查 '{company_name}' 無新聞結果。")
        else:
            print(f"[NEWS/RSS] ✅ 抓取完成，共 {len(out)} 筆。")
            for i, n in enumerate(out[:]):
                print(f"   [{i+1}] {n['title']} | {n['source']}")

        print("[NEWS/RSS] 🏁 Google News RSS 完成。\n")
        return out

    except Exception as e:
        print(f"[NEWS/RSS] ❌ Google News RSS 檢索失敗：{e}")
        return []
