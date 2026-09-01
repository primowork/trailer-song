"""חיפוש קאברים אפיים ממקורות חינמיים (iTunes + Deezer).

המטרה המרכזית של המודול: להחזיר מאגר רחב ומגוון במקום אותה רשימה קבועה.
הדרך: כמה וריאציות שאילתה x כמה מקורות x כמה קטלוגים, ואז מיזוג, ניפוי
כפילויות ודירוג רלוונטיות.
"""
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import httpx
from thefuzz import fuzz

ITUNES_URL = "https://itunes.apple.com/search"
DEEZER_URL = "https://api.deezer.com/search"

# מדינות עם קטלוגים שונים — מרחיב משמעותית את מגוון האמנים שמתקבל
ITUNES_COUNTRIES = ("US", "GB", "DE")

# וריאציות שמכוונות לקאברים אפיים בסגנון טריילר
EPIC_MODIFIERS = (
    "trailer cover",
    "epic cover",
    "cinematic cover",
    "epic trailer version",
    "orchestral cover",
)

# מילים שמסמנות קאבר אפי בכותרת / באלבום
EPIC_KEYWORDS = (
    "trailer", "epic", "cinematic", "orchestral", "cover", "dramatic",
    "hybrid", "score", "remake", "version",
)

EPIC_GENRES = ("soundtrack", "classical", "instrumental", "score")

# אמנים ולייבלים מובילים בתחום הקאברים לטריילרים — משמשים גם לדירוג
# וגם כזרעי חיפוש להרחבת המאגר. קל להוסיף כאן שמות חדשים.
EPIC_SEEDS = (
    "2WEI", "Tommee Profitt", "Hidden Citizens", "UNSECRET", "Fearless Motivators",
    "Take Three Audio", "Ursine Vulpine", "Extreme Music", "Really Slow Motion",
    "Audiomachine", "Two Steps From Hell", "Position Music", "Amadea Music",
    "J2", "Judge & Jury", "Colossal Trailer Music", "Cover Killer", "Violet Orlandi",
)

ALL = "הכל"
LENGTH_SHORT = "קצר (< 3 דק')"
LENGTH_MEDIUM = "בינוני (3-4 דק')"
LENGTH_LONG = "ארוך (> 4 דק')"


# ---------- ניקוי שמות ----------

def clean_artist_name(artist: str) -> str:
    cleaned = re.sub(r"\(.*?\)|\[.*?\]", "", artist or "")
    cleaned = re.sub(r"\b(feat|ft)\b.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_track_title(title: str) -> str:
    """מנקה כותרת לשם חיפוש בפדרציה — משאיר את שם השיר המקורי בלבד."""
    cleaned = re.sub(r"\(.*?\)|\[.*?\]", "", title or "")
    # "from" הוסר בכוונה: הוא חתך כותרות לגיטימיות אחרי שהסוגריים כבר נוקו
    keywords = ["trailer", "cover", "epic", "version", "remix", "cinematic",
                "feat", "ft", "edit", "theme"]
    for kw in keywords:
        cleaned = re.sub(rf"\b{kw}\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-–—]\s*$", "", cleaned)
    return cleaned.strip()


def track_key(artist: str, track: str) -> str:
    """מפתח זהות לשיר — הבסיס לניפוי כפילויות בין אלבומים ובין מקורות."""
    a = re.sub(r"[^\w\s]", "", clean_artist_name(artist).lower()).strip()
    t = re.sub(r"[^\w\s]", "", clean_track_title(track).lower()).strip()
    return f"{a}|{t}"


# ---------- שאילתות ----------

def build_queries(query: str, filters: dict | None = None) -> list[str]:
    """בונה כמה וריאציות שאילתה במקום אחת — זה שורש ההרחבה של המאגר."""
    base = (query or "").strip()
    if not base:
        return []

    queries = [base]
    queries += [f"{base} {modifier}" for modifier in EPIC_MODIFIERS]

    if filters:
        for key in ("style", "tempo"):
            value = filters.get(key)
            if value and value != ALL:
                queries.append(f"{base} {value}")

    # שמירה על סדר ללא כפילויות
    seen, unique = set(), []
    for q in queries:
        low = q.lower()
        if low not in seen:
            seen.add(low)
            unique.append(q)
    return unique


# ---------- מקורות ----------

def _normalize_itunes(item: dict) -> dict | None:
    artist = item.get("artistName") or ""
    track = item.get("trackName") or ""
    if not artist or not track:
        return None
    return {
        "source": "iTunes",
        "uid": f"itunes-{item.get('trackId')}",
        "artist": artist,
        "track": track,
        "album": item.get("collectionName") or "",
        "duration_sec": (item.get("trackTimeMillis") or 0) / 1000,
        "preview_url": item.get("previewUrl") or "",
        "artwork": item.get("artworkUrl100") or "",
        "genre": item.get("primaryGenreName") or "",
    }


def _normalize_deezer(item: dict) -> dict | None:
    artist = (item.get("artist") or {}).get("name") or ""
    track = item.get("title") or ""
    if not artist or not track:
        return None
    return {
        "source": "Deezer",
        "uid": f"deezer-{item.get('id')}",
        "artist": artist,
        "track": track,
        "album": (item.get("album") or {}).get("title") or "",
        "duration_sec": item.get("duration") or 0,
        "preview_url": item.get("preview") or "",
        "artwork": (item.get("album") or {}).get("cover_medium") or "",
        "genre": "",
    }


def itunes_search(term: str, country: str = "US", limit: int = 200,
                  client: httpx.Client | None = None) -> list[dict]:
    params = {
        "term": term, "media": "music", "entity": "song",
        "limit": min(limit, 200), "country": country,
    }
    url = f"{ITUNES_URL}?{urllib.parse.urlencode(params)}"
    try:
        response = (client or httpx).get(url, timeout=10.0)
        results = response.json().get("results", [])
    except Exception:
        return []
    return [t for t in (_normalize_itunes(i) for i in results) if t]


def deezer_search(term: str, limit: int = 100,
                  client: httpx.Client | None = None) -> list[dict]:
    url = f"{DEEZER_URL}?{urllib.parse.urlencode({'q': term, 'limit': min(limit, 100)})}"
    try:
        response = (client or httpx).get(url, timeout=10.0)
        results = response.json().get("data", [])
    except Exception:
        return []
    return [t for t in (_normalize_deezer(i) for i in results) if t]


# ---------- דירוג וניפוי ----------

def score_track(track: dict, query: str) -> int:
    """ציון רלוונטיות: כמה השיר תואם לשאילתה וכמה הוא 'קאבר אפי'."""
    artist = track.get("artist", "")
    title = track.get("track", "")
    album = track.get("album", "")
    haystack = f"{artist} {title} {album}".lower()

    score = max(
        fuzz.token_set_ratio(query.lower(), title.lower()),
        fuzz.token_set_ratio(query.lower(), artist.lower()),
    )

    score += 8 * sum(1 for kw in EPIC_KEYWORDS if kw in haystack)

    if any(g in (track.get("genre", "") or "").lower() for g in EPIC_GENRES):
        score += 15

    if any(fuzz.partial_ratio(seed.lower(), artist.lower()) > 90 for seed in EPIC_SEEDS):
        score += 40

    if not track.get("preview_url"):
        score -= 25  # אי אפשר להאזין — פחות שימושי

    return int(score)


def _passes_length_filter(duration_sec: float, length_filter: str | None) -> bool:
    if not length_filter or length_filter == ALL:
        return True
    if not duration_sec:
        return True  # אין נתון אורך — לא מסננים החוצה
    if length_filter == LENGTH_SHORT:
        return duration_sec < 180
    if length_filter == LENGTH_MEDIUM:
        return 180 <= duration_sec <= 240
    if length_filter == LENGTH_LONG:
        return duration_sec > 240
    return True


def dedupe(tracks: list[dict]) -> list[dict]:
    """שיר זהה מאלבומים שונים או ממקורות שונים -> רשומה אחת.

    נשמר המופע עם הציון הגבוה, בעדיפות למופע שיש לו preview.
    """
    best: dict[str, dict] = {}
    for track in tracks:
        key = track_key(track.get("artist", ""), track.get("track", ""))
        current = best.get(key)
        if current is None:
            best[key] = track
            continue
        has_preview = bool(track.get("preview_url"))
        current_has_preview = bool(current.get("preview_url"))
        if (has_preview, track.get("score", 0)) > (current_has_preview, current.get("score", 0)):
            best[key] = track
    return list(best.values())


def search_covers(query: str, filters: dict | None = None,
                  exclude_keys: frozenset | set = frozenset(),
                  include_seeds: bool = True) -> list[dict]:
    """מחזיר מאגר קאברים ממוין לפי רלוונטיות, ללא כפילויות.

    exclude_keys — שירים שהמשתמש כבר ראה, כדי שחיפוש חוזר יביא חומר חדש.
    """
    queries = build_queries(query, filters)
    if not queries:
        return []

    jobs = []
    for term in queries:
        for country in ITUNES_COUNTRIES:
            jobs.append(("itunes", term, country))
        jobs.append(("deezer", term, None))

    if include_seeds:
        # הרחבה ממוקדת: אותה שאילתה בהקשר של אמני קאברים מובילים
        for seed in EPIC_SEEDS[:6]:
            jobs.append(("itunes", f"{query} {seed}", "US"))
            jobs.append(("deezer", f"{query} {seed}", None))

    collected: list[dict] = []
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        def run(job):
            kind, term, country = job
            try:
                if kind == "itunes":
                    return itunes_search(term, country=country, client=client)
                return deezer_search(term, client=client)
            except Exception:
                # מקור שנופל לא מפיל את החיפוש כולו
                return []

        with ThreadPoolExecutor(max_workers=8) as pool:
            for result in pool.map(run, jobs):
                collected.extend(result)

    scored = []
    for track in collected:
        if not _passes_length_filter(track.get("duration_sec", 0), (filters or {}).get("length")):
            continue
        if track_key(track.get("artist", ""), track.get("track", "")) in exclude_keys:
            continue
        track["score"] = score_track(track, query)
        scored.append(track)

    unique = dedupe(scored)
    unique.sort(key=lambda t: t.get("score", 0), reverse=True)
    return unique
