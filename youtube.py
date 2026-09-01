"""ראיה לשימוש אמיתי בטריילר, מ-YouTube.

לפי ההגדרה שנבחרה, "קאבר לטריילר" הוא כזה ש**שימש בפועל** בטריילר. המטא-דאטה של
חנויות המוזיקה לא מתעדת את זה בשום שדה; YouTube כן, בכותרות ובתיאורים.

המודול מחזיר ראיה גלויה — כותרת סרטון, ערוץ וקישור — ולא פסק דין. המשתמש שופט.

מכסה: 10,000 יחידות ליום, חיפוש עולה 100 = 100 חיפושים ביום. לכן שאילתה אחת לכל
יצירה (לא לכל גרסה) וקאש ל-30 יום.
"""
import os
import re
import time

import httpx

import storage

API_URL = "https://www.googleapis.com/youtube/v3/search"
API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CACHE_FILE = "youtube_evidence.json"
CACHE_TTL = 30 * 24 * 60 * 60

# ביטויים שמעידים על שימוש בטריילר, לא סתם על סגנון "אפי"
TRAILER_PATTERNS = (
    r"\bofficial\s+trailer\b",
    r"\btrailer\s+(music|song|version|cover)\b",
    r"\b(movie|film|game|series)\s+trailer\b",
    r"\btrailer\b.{0,30}\b(soundtrack|ost)\b",
    r"\bas\s+(heard|seen)\s+in\b",
    r"\bfrom\s+the\s+.{0,40}\btrailer\b",
)

_cache: dict | None = None


def available() -> bool:
    return bool(API_KEY)


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        raw = storage._load_json(CACHE_FILE, {}) or {}
        now = time.time()
        _cache = {k: v for k, v in raw.items()
                  if isinstance(v, dict) and now - v.get("cached_at", 0) < CACHE_TTL}
    return _cache


def _save_cache():
    if _cache is not None:
        storage._save_json(CACHE_FILE, _cache)


def looks_like_trailer_use(text: str) -> bool:
    """האם הטקסט מעיד על שימוש בטריילר ולא רק על סגנון."""
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in TRAILER_PATTERNS)


def _query(artist: str, title: str) -> str:
    return f"{artist} {title} trailer".strip()


def search_trailer_evidence(artist: str, title: str, max_results: int = 10,
                            client: httpx.Client | None = None) -> list[dict]:
    """מחזיר ראיות: [{title, channel, url, video_id}]. רשימה ריקה = אין ראיה."""
    if not API_KEY:
        return []

    key = f"{artist.strip().lower()}|{title.strip().lower()}"
    cache = _load_cache()
    if key in cache:
        return cache[key].get("evidence", [])

    params = {
        "part": "snippet", "q": _query(artist, title), "type": "video",
        "maxResults": max_results, "key": API_KEY,
    }
    try:
        response = (client or httpx).get(API_URL, params=params, timeout=15.0)
        if response.status_code != 200:
            return []
        items = response.json().get("items", [])
    except Exception:
        return []

    evidence = []
    for item in items:
        snippet = item.get("snippet") or {}
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue
        haystack = f"{snippet.get('title', '')} {snippet.get('description', '')}"
        if not looks_like_trailer_use(haystack):
            continue
        evidence.append({
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "video_id": video_id,
        })

    cache[key] = {"evidence": evidence, "cached_at": time.time()}
    _save_cache()
    return evidence
