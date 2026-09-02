"""גילוי קאברים לפי יצירה, לא לפי מחרוזת.

הבעיה שהמודול הזה פותר: חיפוש טקסט ב-iTunes מוצא קאבר רק אם מישהו כתב בכותרת שלו
את שם השיר המקורי plus מילה כמו "trailer". קאבר בשם אחר בלתי נראה. מאגר יחסי של
יצירות וביצועים עונה על "כל הגרסאות של השיר הזה" ישירות.

מקור ראשי: SecondHandSongs (כמיליון גרסאות כיסוי ל-100,000 יצירות).
נפילה לאחור: MusicBrainz, שפתוח לגמרי ללא מפתח אך עם כיסוי נמוך יותר.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from thefuzz import fuzz

import search as search_module
from search import has_epic_title
from search import (clean_artist_name, clean_track_title, normalize_artist,
                    normalize_title, score_track, track_key)

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


MAX_WORK_CANDIDATES = 6


def musicbrainz_work_candidates(title: str, artist: str = "",
                                client: httpx.Client | None = None) -> list[dict]:
    """יצירות אפשריות לשם שהוקלד, לבחירת המשתמש.

    השאילתה אינה ביטוי מדויק בכוונה: "Sweet Dreams" חייב להחזיר גם את
    "Sweet Dreams (Are Made of This)" של Eurythmics ולא רק את סטנדרט הקאנטרי
    מ-1955. לקיחת התוצאה הראשונה בעיוורון היא שהחזירה עשרים גרסאות קאנטרי.
    """
    words = " AND ".join(f"work:{w}" for w in re.findall(r"\w+", title))
    if not words:
        return []
    query = words
    if artist:
        query += f' AND artist:"{artist}"'

    payload = _mb_get("work", {"query": query, "limit": 25}, client)
    works = (payload or {}).get("works") or []

    candidates = []
    for work in works:
        work_id, work_title = work.get("id"), work.get("title") or ""
        if not work_id or not work_title:
            continue
        candidates.append({
            "id": work_id,
            "title": work_title,
            "disambiguation": work.get("disambiguation") or "",
            "score": fuzz.token_set_ratio(normalize_title(title), normalize_title(work_title)),
            "writers": ", ".join(
                rel.get("artist", {}).get("name", "")
                for rel in (work.get("relations") or [])
                if rel.get("artist")
            )[:80],
        })

    # התאמת שם קודם, ואז וריאציות ארוכות יותר של אותו שם
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:MAX_WORK_CANDIDATES]


def musicbrainz_versions(title: str, artist: str = "", limit: int = 100,
                         client: httpx.Client | None = None,
                         work_id: str = "") -> list[dict]:
    """כל ההקלטות של היצירה. work_id עוקף את זיהוי היצירה האוטומטי."""
    if not work_id:
        candidates = musicbrainz_work_candidates(title, artist, client)
        if not candidates:
            return []
        work_id = candidates[0]["id"]

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

ENRICH_MATCH_THRESHOLD = 85


def _match_score(version: dict, candidate: dict) -> int:
    """קרבה בין ביצוע מהמאגר לתוצאה מהחנות, על מחרוזות מנורמלות."""
    artist = fuzz.token_set_ratio(normalize_artist(version["artist"]),
                                  normalize_artist(candidate["artist"]))
    title = fuzz.token_set_ratio(normalize_title(version["track"]),
                                 normalize_title(candidate["track"]))
    return min(artist, title)


def _enrich_one(version: dict, client: httpx.Client) -> dict:
    """משלים preview, אורך ואלבום מ-iTunes/Deezer עבור ביצוע שהגיע מהמאגר.

    ההתאמה מטושטשת ולא לפי שוויון מפתח: כותרות חנות כמו
    'California Dreamin\' - From "San Andreas"' לא זהות לשם במאגר, והשוואה מדויקת
    הפילה אותן לרשומה ללא preview.
    """
    term = f"{version['artist']} {version['track']}"
    candidates = search_module.itunes_search(term, limit=10, client=client)
    if not candidates:
        candidates = search_module.deezer_search(term, limit=10, client=client)

    if candidates:
        best = max(candidates, key=lambda c: _match_score(version, c))
        if _match_score(version, best) >= ENRICH_MATCH_THRESHOLD:
            return {**best, **{k: v for k, v in version.items() if v}}

    # לא נמצא בחנויות: הביצוע עדיין רלוונטי כרפרנס, בלי preview
    return {
        "source": version.get("source_db", ""),
        "uid": f"db-{track_key(version['artist'], version['track'])}",
        "artist": version["artist"],
        "track": version["track"],
        "album": "",
        "duration_sec": 0,
        "preview_url": "",
        "artwork": "",
        "genre": "",
        **{k: v for k, v in version.items() if v},
    }


def pick_original(versions: list[dict], artist: str = "") -> dict | None:
    """מזהה את הגרסה המקורית — הבסיס להשוואה.

    האמן שהמשתמש הקליד קודם; אחרת המוקדמת ביותר לפי שנה.
    """
    if not versions:
        return None
    if artist:
        target = normalize_artist(artist)
        for version in versions:
            if fuzz.ratio(target, normalize_artist(version.get("artist", ""))) > 90:
                return version
    # גרסה בלי preview חסרת ערך כבסיס השוואה: אי אפשר למדוד מולה כלום
    playable = [v for v in versions if v.get("preview_url")]
    pool = playable or versions

    dated = [v for v in pool if str(v.get("year", "")).strip().isdigit()]
    if dated:
        return min(dated, key=lambda v: int(str(v["year"])[:4]))
    return pool[0]


def find_epic_versions(title: str, artist: str = "",
                       limit: int = 60) -> tuple[list[dict], str]:
    """גרסאות שמציגות את עצמן כטריילר אפי, ישירות מהחנויות.

    לשונית הקאברים מושכת את *כל* הגרסאות של היצירה מהמאגר, ולכן היא מחזירה
    בעיקר קאברים נעימים. גרסאות טריילר נקראות בפועל "Epic Trailer Version"
    בכותרת, ולכן מוצאים אותן בחיפוש בחנויות ולא בסינון רשימת היצירה.
    """
    clean = clean_track_title(title) or title
    results = search_module.search_covers(clean, origin_artist=artist,
                                          include_seeds=True, prefer_new=False)

    # לא לכלול את הביצוע המקורי עצמו
    if artist:
        original = normalize_artist(artist)
        results = [t for t in results
                   if normalize_artist(t.get("artist", "")) != original]

    # הכותרת מכניסה, אבל אינה מוציאה: רמיקס יכול להיות גרסה ענקית גם אם לא
    # כתוב בו "epic". מי שלא הכריז על עצמו נשאר ברשימה ונמדד לפי גודל.
    for track in results:
        track["epic_by_title"] = has_epic_title(track)

    results.sort(key=lambda t: (t["epic_by_title"], t.get("score", 0)), reverse=True)
    return results[:limit], "חיפוש בחנויות"


def find_covers(title: str, artist: str = "",
                limit: int = 80, work_id: str = "") -> tuple[list[dict], str, dict | None]:
    """מחזיר (גרסאות, שם המקור ששימש בפועל).

    מנסה SecondHandSongs, ונופל ל-MusicBrainz אם הוא לא זמין או לא החזיר דבר.
    """
    clean_title = clean_track_title(title) or title
    versions, source_used = [], ""

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        if work_id:
            # המשתמש בחר יצירה מפורשות — מדלגים על הזיהוי האוטומטי
            versions = musicbrainz_versions(clean_title, artist, client=client, work_id=work_id)
            source_used = "MusicBrainz" if versions else ""
            work = None
        else:
            work = shs_search_work(clean_title, artist, client)
        if work:
            versions = shs_list_versions(work, client)
            if versions:
                source_used = "SecondHandSongs"

        if not versions and not work_id:
            versions = musicbrainz_versions(clean_title, artist, client=client)
            if versions:
                source_used = "MusicBrainz"

        if not versions:
            return [], "", None

        original_version = pick_original(versions, artist)

        # לא לכלול את הביצוע המקורי עצמו כשחיפשו לפי אמן
        if artist:
            original = clean_artist_name(artist).lower()
            versions = [v for v in versions
                        if clean_artist_name(v["artist"]).lower() != original]

        # הסינון אינו כאן בכוונה: לפני ההעשרה יש רק אמן וכותרת מהמאגר, ולכן
        # שלושה מתוך חמשת הסימנים (שיבוץ בפסקול, ז'אנר, סמן בכותרת החנות) אינם
        # יכולים להתקיים. גרסה כמו 'California Dreamin\' (From "San Andreas")'
        # הייתה נופלת כאן עוד לפני שהתגלה שיש לה סימן. הסינון מתבצע אחרי ההעשרה.
        versions = versions[:limit]

        to_enrich = list(versions)
        if original_version and original_version not in to_enrich:
            to_enrich.append(original_version)

        with ThreadPoolExecutor(max_workers=8) as pool:
            enriched_all = list(pool.map(lambda v: _enrich_one(v, client), to_enrich))

        original = enriched_all[-1] if (original_version
                                        and original_version not in versions) else None
        enriched = enriched_all[:len(versions)]
        if original is None and original_version:
            index = versions.index(original_version)
            original = enriched[index]

    # שתי גרסאות שונות מהמאגר יכולות להתאים לאותה תוצאה בחנות ולקבל אותו uid.
    # Streamlit קורס על מפתח widget כפול, ולכן הייחודיות נאכפת על שניהם.
    seen, seen_uids, unique = set(), set(), []
    for item in enriched:
        key = track_key(item["artist"], item["track"])
        if key in seen:
            continue
        seen.add(key)
        if item.get("uid") in seen_uids:
            item["uid"] = f"{item['uid']}-{len(seen_uids)}"
        seen_uids.add(item["uid"])
        item["score"] = score_track(item, clean_title)
        unique.append(item)

    unique.sort(key=lambda t: t.get("score", 0), reverse=True)
    return unique, source_used, original
