# rag.py（含完整 LOG 版 + 支援背景刷新重新載入）
import time
from retrievers.cache import (
    load_stock_map_from_cache,
    get_price_with_cache,
    get_news_with_cache,
)
from retrievers.news import fetch_news_rss
from retrievers.merge_utils import merge_news
from retrievers.fulltext import lazy_fulltext_topk
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    """把 URL 正規化：http->https、移除空白、修正特定網域、處理解析失敗"""
    if not url:
        return ""
    url = url.strip()

    # http -> https（LINE/瀏覽器通常更穩）
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            return ""

        host = (p.netloc or "").lower()

        # 你的例子：sinotrade.com.tw -> www.sinotrade.com.tw（可選）
        if host == "sinotrade.com.tw":
            p = p._replace(netloc="www.sinotrade.com.tw")

        return urlunparse(p)
    except Exception:
        return ""


def looks_like_article(url: str) -> bool:
    """判斷是不是『文章頁』而不是首頁。規則可再調，但先用這個就很有效。"""
    if not url:
        return False
    try:
        p = urlparse(url)
        # 首頁（path="" 或 "/"）視為無效
        if p.path in ("", "/") and not p.query:
            return False
        return True
    except Exception:
        return False


# === 股票代號對照表 ===
print("[RAG/Init] 🧭 載入 FinMind 股票代號清單中...")
STOCK_MAP = load_stock_map_from_cache()
print(f"[RAG/Init] ✅ 已載入 {len(STOCK_MAP)//2} 檔股票代號。")

# === 使用者查詢快取 ===
CACHE = {}
CACHE_DURATION_SECONDS = 120


# ---------------------------------------------------------
# 公司辨識
# ---------------------------------------------------------
def smart_identify_company(query: str):
    q = query.strip().upper()
    print(f"[RAG/Identify] 🔍 嘗試辨識公司：'{q}'")

    # 完全命中（名稱或代號）
    if q in STOCK_MAP:
        print(f"[RAG/Identify] ✅ 完全命中 STOCK_MAP → {q} → {STOCK_MAP[q]}")
        return STOCK_MAP[q], q

    # 模糊比對
    for name in STOCK_MAP.keys():
        if len(name) >= 2 and name in q:
            print(f"[RAG/Identify] 🔍 偵測到公司名稱片段 → {name}")
            return STOCK_MAP[name], name

    print(f"[RAG/Identify] ❌ 找不到匹配的公司 → '{q}'")
    return None, None


# ---------------------------------------------------------
# 主流程：組合 context
# ---------------------------------------------------------
def build_context(query: str):
    user_text = query.strip()
    now = time.time()
    print(f"[RAG/Query] 🚀 收到使用者查詢：「{user_text}」")

    # --- 快取檢查 ---
    if user_text in CACHE and now < CACHE[user_text]['expires_at']:
        print(f"[RAG/Cache] ✅ 使用快取資料 → '{user_text}'（剩餘 {int(CACHE[user_text]['expires_at'] - now)} 秒）")
        return CACHE[user_text]['data']
    print(f"[RAG/Cache] ❌ 快取未命中，開始查詢資料 → '{user_text}'\n")

    # --- 公司辨識 ---
    ticker_id, company_name = smart_identify_company(user_text)
    if not ticker_id:
        print(f"[RAG/Query] ❌ 查無公司 '{user_text}'，終止流程。")
        return f"抱歉，找不到與「{user_text}」相關的公司，請確認名稱或代號是否正確。"
    print(f"[RAG/Query] ✅ 公司辨識完成：{company_name}（代號 {ticker_id}）\n")

    # --- 股價查詢 ---
    print(f"[RAG/Price] 💹 開始查詢股價 → {ticker_id}")
    price = get_price_with_cache(ticker_id)
    if price:
        print(f"[RAG/Price] ✅ 股價結果：{price['price']} ({'+' if price['change']>=0 else ''}{price['change']}, {price['pct']}%)\n")
    else:
        print(f"[RAG/Price] ⚠️ 無法取得股價資料。")

    # --- 新聞抓取 ---
    print(f"[RAG/News] 🗞️ 開始抓取新聞 → FinMind + Google RSS")
    finmind_news = get_news_with_cache(ticker_id, company_name) or []
    rss_news = fetch_news_rss(company_name, ticker_id) or []

    # --- 合併新聞 ---
    print(f"[RAG/NewsMerge] 🔄 準備合併 FinMind 與 RSS 新聞...")
    merged_news = merge_news(finmind_news, rss_news)
    print(f"[RAG/NewsMerge] ✅ 合併完成，共 {len(merged_news)} 則。\n")

    # --- 組裝 context ---
    print(f"[RAG/Context] 🧩 組裝 context 文字內容...")
    ctx_lines = []

    if price:
        ctx_lines.append(f"[股價資訊] {ticker_id} 現價 {price['price']} ({'+' if price['change']>=0 else ''}{price['change']} / {price['pct']}%)")

    if merged_news:
        ctx_lines.append("[新聞來源 (請用 [編號] 引用)]")
        for i, n in enumerate(merged_news, start=1):
            title = (n.get("title") or "").strip()
            src = (n.get("source") or "").strip() or "未知來源"
            dt = (n.get("publishedAt") or "").strip() or "未知日期"
            raw_url = (n.get("url") or "").strip()
            norm_url = normalize_url(raw_url)
            if not looks_like_article(norm_url):
                norm_url = ""
            # ✅ 把正規化後的結果寫回去，讓後面的 lazy full-text 用得到乾淨 URL
            n["url"] = norm_url
            url = norm_url if norm_url else "無連結"

            # 這行就是 grounding 的核心：LLM 之後就能用 [i]
            ctx_lines.append(f"[{i}] {title} | {src} | {dt} | {url}")

    # --- Lazy Full-Text Top3（只抓最相關的 3 篇全文）---
    ft_map = lazy_fulltext_topk(user_text, merged_news, k=3)
    if ft_map:
        ctx_lines.append("")
        ctx_lines.append("[全文摘錄 (Top3，仍請用相同 [編號] 引用)]")
        for idx in sorted(ft_map.keys()):
            for j, snippet in enumerate(ft_map[idx], start=1):
                ctx_lines.append(f"[{idx}] 摘錄{j}: {snippet}")

    if not ctx_lines:
        result = f"(抱歉，找不到關於「{user_text}」的即時資訊)"
        print(f"[RAG/Context] ⚠️ 未取得任何股價或新聞資料。")
    else:
        result = "\n".join(ctx_lines)
        print(f"[RAG/Context] ✅ 組裝完成，共 {len(merged_news)} 則新聞。\n")

    # --- 寫入快取 ---
    CACHE[user_text] = {'data': result, 'expires_at': now + CACHE_DURATION_SECONDS}
    print(f"[RAG/Cache] 💾 已快取結果 → '{user_text}'（有效 {CACHE_DURATION_SECONDS} 秒）")

    print(f"[RAG/Done] 🏁 查詢流程結束：'{user_text}'\n")
    #print(f"{result}\n")
    return result


# ---------------------------------------------------------
# 背景刷新後重新載入股票代號（由 cache.py 呼叫）
# ---------------------------------------------------------
def refresh_stock_map():
    """由 cache.py 背景更新完成後呼叫，用於重新載入最新 STOCK_MAP"""
    print("[RAG/Init] 🧭 載入 FinMind 股票代號清單中（背景刷新後）...")
    from retrievers.cache import load_stock_map_from_cache
    global STOCK_MAP
    STOCK_MAP = load_stock_map_from_cache()
    print(f"[RAG/Init] ✅ 已重新載入 {len(STOCK_MAP)//2} 檔股票代號。")
