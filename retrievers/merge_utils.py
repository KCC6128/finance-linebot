# retrievers/merge_utils.py（含 LOG 版）
from typing import List, Dict

def merge_news(finmind_news: List[Dict], rss_news: List[Dict], take_each: int = 4, cap: int = 8) -> List[Dict]:
    print("[LOG/NewsMerge] 🧩 開始合併 FinMind + Google RSS 新聞")
    print(f"[LOG/NewsMerge] FinMind 原始數量：{len(finmind_news)}，RSS 原始數量：{len(rss_news)}")

    # 標記來源
    f_sub = []
    for n in finmind_news[:take_each]:
        n = dict(n)
        n["_source_tag"] = "finmind"
        n.setdefault("source", "FinMind")
        f_sub.append(n)
    print(f"[LOG/NewsMerge] 已取 FinMind 前 {len(f_sub)} 則")

    r_sub = []
    for n in rss_news[:take_each]:
        n = dict(n)
        n["_source_tag"] = "rss"
        n.setdefault("source", "Google RSS")
        r_sub.append(n)
    print(f"[LOG/NewsMerge] 已取 RSS 前 {len(r_sub)} 則")

    # 資料不足互補
    if len(f_sub) < take_each and len(rss_news) > take_each:
        extra = take_each - len(f_sub)
        r_sub = rss_news[:take_each + extra]
        print(f"[LOG/NewsMerge] ⚠️ FinMind 不足 {len(f_sub)} 則，從 RSS 補 {extra} 則（RSS 總數：{len(r_sub)}）")

    if len(r_sub) < take_each and len(finmind_news) > take_each:
        extra = take_each - len(r_sub)
        f_sub = finmind_news[:take_each + extra]
        print(f"[LOG/NewsMerge] ⚠️ RSS 不足 {len(r_sub)} 則，從 FinMind 補 {extra} 則（FinMind 總數：{len(f_sub)}）")

    # 交錯取樣
    raw = []
    m = max(len(f_sub), len(r_sub))
    for i in range(m):
        if i < len(f_sub):
            raw.append(f_sub[i])
        if i < len(r_sub):
            raw.append(r_sub[i])
    print(f"[LOG/NewsMerge] 🔄 交錯取樣完成，共 {len(raw)} 則候選新聞")

    # 去重（以標題）
    seen = set()
    merged = []
    for n in raw:
        title = (n.get("title") or "").strip()
        src = n.get("source", "") or "未知來源"
        if not title:
            print(f"[LOG/NewsMerge] ⚠️ 略過無標題新聞（來源：{src}）")
            continue
        if title in seen:
            print(f"[LOG/NewsMerge] 🔁 偵測重複標題「{title}」，已略過（來源：{src}）")
            continue
        seen.add(title)
        merged.append(n)

    if len(merged) == 0:
        print("[LOG/NewsMerge] ⚠️ 沒有任何可用新聞（兩方皆空或全重複）")

    return merged[:cap]
