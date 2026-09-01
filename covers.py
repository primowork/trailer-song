"""גילוי קאברים לפי יצירה, לא לפי מחרוזת.

הבעיה שהמודול הזה פותר: חיפוש טקסט ב-iTunes מוצא קאבר רק אם מישהו כתב בכותרת שלו
את שם השיר המקורי plus מילה כמו "trailer". קאבר בשם אחר בלתי נראה. מאגר יחסי של
יצירות וביצועים עונה על "כל הגרסאות של השיר הזה" ישירות.

מקור ראשי: SecondHandSongs (כמיליון גרסאות כיסוי ל-100,000 יצירות).
נפילה לאחור: MusicBrainz, שפתוח לגמרי ללא מפתח אך עם כיסוי נמוך יותר.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from thefuzz import fuzz

import search as search_module
from search import EPIC_SEEDS, clean_artist_name, clean_track_title, score_track, track_key

SHS_BASE = os.environ.get("SHS_API_URL", "https://secondhandsongs.com/api")
SHS_TOKEN = os.environ.get("SHS_API_TOKEN", "")

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
# MusicBrainz דורש User-Agent מזהה ומגביל לבקשה אחת לשנייה
MB_USER_AGENT = os.environ.get(
    "MUSICBRAINZ_USER_AGENT", "trailer-song/2.0 (https://github.com/primowork/trailer-song)"
)
MB_MIN_INTERVAL = 1.0

_last_mb_call = 0.0


def _shs_headers() -> dict:
    headers = {"Accept": "application/json", "User-Agent": MB_USER_AGENT}
    if SHS_TOKEN:
        headers["Authorization"] = f"Bearer {SHS_TOKEN}"
    return headers


# ---------- SecondHandSongs ----------

def shs_search_work(title: str, artist: str = "", client: httpx.Client | None = None) -> dict | None:
    """מאתר את היצירה המקורית. מחזיר None אם לא נמצאה או שה-API לא זמין."""
    params = {"title": title, "pageSize": 10}
    if artist:
        params["performer"] = artist
    try:
        response = (client or httpx).get(
            f"{SHS_BASE}/search/work", params=params, headers=_shs_headers(), timeout=15.0
        )
        if response.status_code != 200:
            return None
        results = response.json().get("resultPage") or response.json().get("results") or []
    except Exception:
        return None

    if not results:
        return None

    # הטוב ביותר לפי התאמת כותרת, לא בהכרח הראשון
    def title_score(item):
        return fuzz.token_set_ratio(title.lower(), (item.get("title") or "").lower())

    return max(results, key=title_score)


def shs_list_versions(work: dict, client: httpx.Client | None = None) -> list[dict]:
    """כל הביצועים המוקלטים של היצירה."""
    uri = work.get("uri") or work.get("versionsUri")
    if not uri:
        return []
    try:
        response = (client or httpx).get(uri, headers=_shs_headers(), timeout=15.0)
        if response.status_code != 200:
            return []
        payload = response.json()
    except Exception:
        return []

    versions = payload.get("versions") or payload.get("performances") or []
    out = []
    for version in versions:
        performer = version.get("performer") or {}
        name = performer.get("name") if isinstance(performer, dict) else str(performer)
        if not name:
            continue
        out.append({
            "artist": name,
            "track": version.get("title") or work.get("title") or "",
            "year": version.get("date") or "",
            "source_db": "SecondHandSongs",
        })
    return out


# ---------- MusicBrainz (נפילה לאחור) ----------

def _mb_get(path: str, params: dict, client: httpx.Client | None = None):
    """כיבוד מגבלת הקצב של MusicBrainz: בקשה אחת לשנייה."""
    global _last_mb_call
    elapsed = time.time() - _last_mb_call
    if elapsed < MB_MIN_INTERVAL:
        time.sleep(MB_MIN_INTERVAL - elapsed)
    _last_mb_call = time.time()

    params = {**params, "fmt": "json"}
    try:
        response = (client or httpx).get(
            f"{MUSICBRAINZ_BASE}/{path}", params=params,
            headers={"User-Agent": MB_USER_AGENT}, timeout=15.0,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def musicbrainz_versions(title: str, artist: str = "", limit: int = 100,
                         client: httpx.Client | None = None) -> list[dict]:
    """כל ההקלטות הנושאות את שם היצירה, דרך ה-work של MusicBrainz."""
    query = f'work:"{title}"'
    if artist:
        query += f' AND artist:"{artist}"'
    payload = _mb_get("work", {"query": query, "limit": 5}, client)
    works = (payload or {}).get("works") or []
    if not works:
        return []

    work_id = works[0].get("id")
    if not work_id:
        return []

    payload = _mb_get("recording", {"work": work_id, "limit": limit, "inc": "artist-credits+isrcs"}, client)
    recordings = (payload or {}).get("recordings") or []

    out = []
    for recording in recordings:
        credits = recording.get("artist-credit") or []
        name = credits[0].get("name") if credits else ""
        if not name:
            continue
        isrcs = recording.get("isrcs") or []
        out.append({
            "artist": name,
            "track": recording.get("title") or title,
            "year": (recording.get("first-release-date") or "")[:4],
            "isrc": isrcs[0] if isrcs else "",
            "source_db": "MusicBrainz",
        })
    return out


# ---------- העשרה ודירוג ----------

def _enrich_one(version: dict, client: httpx.Client) -> dict:
    """משלים preview, אורך ואלבום מ-iTunes/Deezer עבור ביצוע שהגיע מהמאגר."""
    term = f"{version['artist']} {version['track']}"
    candidates = search_module.itunes_search(term, limit=10, client=client)
    if not candidates:
        candidates = search_module.deezer_search(term, limit=10, client=client)

    target = track_key(version["artist"], version["track"])
    for candidate in candidates:
        if track_key(candidate["artist"], candidate["track"]) == target:
            return {**candidate, **{k: v for k, v in version.items() if v}}

    # לא נמצא בחנויות: הביצוע עדיין רלוונטי כרפרנס, בלי preview
    return {
        "source": version.get("source_db", ""),
        "uid": f"db-{target}",
        "artist": version["artist"],
        "track": version["track"],
        "album": "",
        "duration_sec": 0,
        "preview_url": "",
        "artwork": "",
        "genre": "",
        **{k: v for k, v in version.items() if v},
    }


def is_epic_performer(artist: str) -> bool:
    """האם המבצע מזוהה עם עולם מוזיקת הטריילרים."""
    lowered = clean_artist_name(artist).lower()
    return any(fuzz.partial_ratio(seed.lower(), lowered) > 90 for seed in EPIC_SEEDS)


def find_covers(title: str, artist: str = "", epic_only: bool = False,
                limit: int = 80) -> tuple[list[dict], str]:
    """מחזיר (גרסאות, שם המקור ששימש בפועל).

    מנסה SecondHandSongs, ונופל ל-MusicBrainz אם הוא לא זמין או לא החזיר דבר.
    """
    clean_title = clean_track_title(title) or title
    versions, source_used = [], ""

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        work = shs_search_work(clean_title, artist, client)
        if work:
            versions = shs_list_versions(work, client)
            if versions:
                source_used = "SecondHandSongs"

        if not versions:
            versions = musicbrainz_versions(clean_title, artist, client=client)
            if versions:
                source_used = "MusicBrainz"

        if not versions:
            return [], ""

        # לא לכלול את הביצוע המקורי עצמו כשחיפשו לפי אמן
        if artist:
            original = clean_artist_name(artist).lower()
            versions = [v for v in versions
                        if clean_artist_name(v["artist"]).lower() != original]

        if epic_only:
            versions = [v for v in versions if is_epic_performer(v["artist"])]

        versions = versions[:limit]

        with ThreadPoolExecutor(max_workers=8) as pool:
            enriched = list(pool.map(lambda v: _enrich_one(v, client), versions))

    seen, unique = set(), []
    for item in enriched:
        key = track_key(item["artist"], item["track"])
        if key in seen:
            continue
        seen.add(key)
        item["score"] = score_track(item, clean_title)
        item["is_epic_performer"] = is_epic_performer(item["artist"])
        if item["is_epic_performer"]:
            item["score"] += 30
        unique.append(item)

    unique.sort(key=lambda t: t.get("score", 0), reverse=True)
    return unique, source_used
