# retrievers/fulltext.py
from __future__ import annotations

import re
import time
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# 簡單的 in-memory cache，避免同一篇文章一直抓
_FULLTEXT_CACHE: Dict[str, Dict] = {}
_FULLTEXT_TTL_SECONDS = 60 * 60  # 1 hour

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _now() -> float:
    return time.time()


def _normalize_ws(s: str) -> str:
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _tokenize(text: str) -> List[str]:
    """
    兼容中英：把「中文連續字 / 英數單字」都當 token。
    """
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,}", text)
    # 去掉太短的 token（例如單一字很容易太雜）
    out = []
    for t in tokens:
        t = t.strip().lower()
        if len(t) <= 1:
            continue
        out.append(t)
    return out


def _overlap_score(query_tokens: List[str], doc_text: str) -> int:
    """
    超輕量打分：query token 出現幾次（重疊數量）
    """
    if not query_tokens or not doc_text:
        return 0
    dt = doc_text.lower()
    return sum(1 for t in query_tokens if t in dt)

def _looks_like_article(url: str) -> bool:
    if not url:
        return False
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
        if p.path in ("", "/") and not p.query:
            return False
        if len(p.path.strip("/")) < 5:
            return False
        return True
    except Exception:
        return False

def fetch_fulltext(url: str, timeout: int = 10, max_chars: int = 20000) -> str:
    """
    抓網頁並萃取可讀文字。失敗回傳空字串。
    """
    if not url:
        return ""

    # cache hit
    item = _FULLTEXT_CACHE.get(url)
    if item and _now() < item["expires_at"]:
        return item["text"]

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
        )
        resp.raise_for_status()
    except Exception:
        return ""

    html = resp.text or ""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # 移除干擾
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    # 優先取 <article>
    main = soup.find("article")
    if main is None:
        # 次選：main/content/body
        main = soup.find("main") or soup.find(attrs={"id": "content"}) or soup.body

    if main is None:
        return ""

    text = main.get_text(separator="\n")
    text = _normalize_ws(text)

    # 太短通常是擋爬/空殼頁
    if len(text) < 200:
        return ""

    if len(text) > max_chars:
        text = text[:max_chars]

    _FULLTEXT_CACHE[url] = {"text": text, "expires_at": _now() + _FULLTEXT_TTL_SECONDS}
    return text


def select_topk_by_title(query: str, news_list: List[Dict], k: int = 3) -> List[int]:
    """
    只用「title」做 lazy rerank：挑最相關的 TopK（回傳 index，0-based）
    """
    q_tokens = _tokenize(query)
    scored: List[Tuple[int, int]] = []
    for i, n in enumerate(news_list):
        title = (n.get("title") or "").strip()
        if not title:
            continue
        score = _overlap_score(q_tokens, title)
        scored.append((score, i))

    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    top = [i for score, i in scored[:k] if score > 0]

    # 如果 query token 在標題都打不到（很常見），就退回拿前 k 篇（但仍避免空 title）
    if not top:
        top = [i for i, n in enumerate(news_list) if (n.get("title") or "").strip()][:k]

    return top


def extract_top_snippets(query: str, fulltext: str, max_snippets: int = 2) -> List[str]:
    """
    從全文中切出最相關的片段（超輕量：滑動視窗 + token overlap）
    """
    if not fulltext:
        return []

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    # 先分段（以空行）
    paras = [p.strip() for p in fulltext.split("\n\n") if p.strip()]
    # 過濾很短段落
    paras = [p for p in paras if len(p) >= 80]

    if not paras:
        return []

    scored: List[Tuple[int, str]] = []
    for p in paras:
        score = _overlap_score(q_tokens, p)
        if score <= 0:
            continue
        scored.append((score, p))

    # 如果段落打不到，就退一步用整篇做 windows
    if not scored:
        text = fulltext
        window = 360
        stride = 180
        for start in range(0, max(1, len(text) - window), stride):
            chunk = text[start : start + window].strip()
            if len(chunk) < 120:
                continue
            score = _overlap_score(q_tokens, chunk)
            if score > 0:
                scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    for score, s in scored:
        s = _normalize_ws(s)
        # 控制輸入長度（避免 context 爆掉）
        if len(s) > 380:
            s = s[:380] + "..."
        if s not in out:
            out.append(s)
        if len(out) >= max_snippets:
            break
    return out


def lazy_fulltext_topk(rank_query: str, snippet_query: str, news_list: List[Dict], k: int = 3) -> Dict[int, List[str]]:
    top_idx_0 = select_topk_by_title(rank_query, news_list, k=k)
    result: Dict[int, List[str]] = {}

    for i0 in top_idx_0:
        n = news_list[i0]
        url = (n.get("url") or "").strip()
        if (not url) or (not _looks_like_article(url)):
            continue

        text = fetch_fulltext(url)
        snippets = extract_top_snippets(snippet_query, text, max_snippets=2)
        if snippets:
            result[i0 + 1] = snippets

    return result

