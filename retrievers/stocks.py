# retrievers/stocks.py（含 LOG 版）
import requests
from datetime import datetime, timedelta

def fetch_price_finmind(symbol_id: str, api_key: str):
    """
    使用 FinMind API 的 TaiwanStockPrice 資料集獲取股價。
    這個方法專為台股設計，非常穩定。
    
    Args:
        symbol_id (str): 純數字的股票代號 (例如 '2330')。
        api_key (str): 您的 FinMind API Token。
    
    Returns:
        dict: 包含股價詳細資訊的字典，或 None。
    """
    print(f"[STOCKS/FinMind] ⏳ 從 FinMind 抓取股價 → {symbol_id}")

    # 設定 API 的 URL 和參數
    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    
    params = {
        'dataset': 'TaiwanStockPrice',
        'data_id': symbol_id,
        'start_date': start_date,
        'token': api_key,
    }

    try:
        print(f"[STOCKS/FinMind] 🔗 API 請求中（symbol={symbol_id}, start={start_date}）...")
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()

        # 檢查 API 是否成功回傳資料
        stock_data = data.get('data')
        if not stock_data or len(stock_data) < 2:
            print(f"[STOCKS/FinMind] ⚠️ 回傳資料不足兩筆，無法計算漲跌。({len(stock_data) if stock_data else 0} 筆)")
            return None

        print(f"[STOCKS/FinMind] ✅ API 成功回傳 {len(stock_data)} 筆資料。")

        # --- 解析與計算 ---
        latest_data = stock_data[-1]
        previous_data = stock_data[-2]

        close = latest_data.get('close', 0)
        prev_close = previous_data.get('close', 0)
        change = close - prev_close
        pct = (change / prev_close * 100) if prev_close else 0.0

        # --- 格式化結果 ---
        result = {
            "symbol": latest_data.get('stock_id'),
            "price": round(close, 2),
            "change": round(change, 2),
            "pct": round(pct, 2),
            "currency": "TWD"
        }

        print(f"[STOCKS/FinMind] 📊 股價計算完成：{result['symbol']} 收盤 {result['price']} ({'+' if result['change']>=0 else ''}{result['change']} / {result['pct']}%)")
        return result

    except Exception as e:
        print(f"[STOCKS/FinMind] ❌ 抓取 {symbol_id} 時發生錯誤：{e}\n")
        return None
