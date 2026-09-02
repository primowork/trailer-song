"""מצעדים חיים מ-Deezer: קטגוריות ושירים, בלי מפתח ובלי גרידה.

הבחירה ב-Deezer אינה שרירותית: `api.deezer.com` הוא בדיוק המארח שהאפליקציה כבר
מדברת איתו בהצלחה בכל חיפוש, ולכן מצעד ממנו יעבוד בדיפלוימנט. מקור שלא נבדק
בסביבה שבה הוא ירוץ הוא הימור, וכבר שילמנו עליו כאן.

המצעדים משמשים כאינדקס: קליק על שיר ממלא את שדות החיפוש ומריץ חיפוש קאברים.
"""
import storage
from search import _normalize_deezer, get_json

DEEZER_CHART = "https://api.deezer.com/chart"
DEEZER_GENRE = "https://api.deezer.com/genre"

CACHE_FILE = "charts.json"
CACHE_TTL = 6 * 60 * 60      # מצעד משתנה לאט; שש שעות חוסכות קריאות בכל rerun
# תוכן ה-expander ב-Streamlit מרונדר גם כשהוא סגור, ולכן כישלון נשמר לזמן קצר:
# בלעדיו כל rerun היה משלם שלושה ניסיונות חוזרים על אותה קריאה שנופלת.
FAILURE_TTL = 5 * 60
CHART_LIMIT = 50

ALL_GENRES = 0               # ה-id של "הכל" ב-Deezer

_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = storage._load_json(CACHE_FILE, {}) or {}
    return _cache


def _cached(key: str, fetch):
    import time

    cache = _load_cache()
    entry = cache.get(key)
    if entry:
        ttl = CACHE_TTL if entry.get("value") else FAILURE_TTL
        if time.time() - entry.get("at", 0) < ttl:
            return entry["value"]

    value = fetch()
    cache[key] = {"at": time.time(), "value": value}
    if value:
        storage._save_json(CACHE_FILE, cache)
    return value


def genres() -> list[dict]:
    """קטגוריות המוזיקה של Deezer, כרשימת [{'id', 'name'}]."""
    def fetch():
        payload = get_json(DEEZER_GENRE)
        items = (payload or {}).get("data") or []
        return [{"id": item["id"], "name": item["name"]}
                for item in items if item.get("id") is not None and item.get("name")]

    return _cached("genres", fetch) or []


def chart_tracks(genre_id: int = ALL_GENRES, limit: int = CHART_LIMIT) -> list[dict]:
    """שירי המצעד בקטגוריה, בפורמט הטראק הרגיל של המערכת."""
    def fetch():
        payload = get_json(f"{DEEZER_CHART}/{int(genre_id)}/tracks",
                           params={"limit": min(limit, 100)})
        items = (payload or {}).get("data") or []
        return [t for t in (_normalize_deezer(item) for item in items) if t]

    return _cached(f"tracks:{genre_id}:{limit}", fetch) or []


def chart_artists(genre_id: int = ALL_GENRES, limit: int = CHART_LIMIT) -> list[str]:
    """אמני המצעד בקטגוריה, כשמות בלבד — הם מזינים את החיפוש לפי אמן."""
    def fetch():
        payload = get_json(f"{DEEZER_CHART}/{int(genre_id)}/artists",
                           params={"limit": min(limit, 100)})
        items = (payload or {}).get("data") or []
        return [item["name"] for item in items if item.get("name")]

    return _cached(f"artists:{genre_id}:{limit}", fetch) or []
