"""חיפוש קאברים אפיים ממקורות חינמיים (iTunes + Deezer).

המטרה המרכזית של המודול: להחזיר מאגר רחב ומגוון במקום אותה רשימה קבועה.
הדרך: כמה וריאציות שאילתה x כמה מקורות x כמה קטלוגים, ואז מיזוג, ניפוי
כפילויות ודירוג רלוונטיות.
"""
import datetime as _dt
import os
import re
import threading
import time
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
    "soundtrack",
    "official soundtrack",
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

# אמנים מיינסטרים שהקאברים שלהם שימשו בטריילרים. קטגוריה נפרדת מ-EPIC_SEEDS
# בכוונה: אלה לא חברות מוזיקת טריילרים אלא זמרים מוכרים שעשו קאבר לשיר ישן.
# הדוגמה המכוננת: Sia - California Dreamin' בטריילר של San Andreas.
TRAILER_COVER_ARTISTS = (
    "Sia", "Jasmine Thompson", "Ruelle", "Fleurie", "Aurora", "Birdy",
    "Lorde", "Gary Clark Jr", "Hozier", "Chris Cornell", "Halsey",
    "Billie Eilish", "Lana Del Rey", "Gabrielle Aplin", "Alice Merton",
    "Zayde Wolf", "Nathan Wagner", "Beth Crowley", "Karen O",
)

# סגנונות לחיפוש. הרשימה הקודמת הכילה ארבעה; אלה מונחים שבאמת מחזירים חומר שונה
# כשהם נוספים לשאילתה, ולא וריאציות של אותו דבר.
STYLES = (
    "Epic Orchestral", "Dark Orchestral", "Hybrid Orchestral",
    "Rock Hybrid", "Metal Cover", "Industrial",
    "Dark Electronic", "Synthwave", "Dubstep Drop", "Trap Hybrid",
    "Dramatic Piano", "Solo Piano", "Female Vocal", "Male Vocal", "Choir",
    "Strings Only", "Percussion Heavy", "Ambient Build", "Horror", "Western",
    "Gospel Soul", "Acoustic Stripped", "Lo-fi", "Retro 80s",
)

# סמנים שאמנים כותבים בכותרת של גרסת טריילר אפית בפועל. זה חיפוש, לא סיווג:
# אנחנו מוצאים טראקים שקוראים לעצמם כך, ולא טוענים שהם שימשו בטריילר.
EPIC_TITLE_MARKERS = (
    "trailer",
    # trailerized: מונח מקצועי לגרסה שעובדה מחדש לשימוש בטריילר
    "trailerized",
    "epic", "cinematic", "orchestral", "dramatic", "dark",
    "cover version", "remake", "reimagined",
)


def has_epic_title(track: dict) -> bool:
    """האם הטראק עצמו מציג את עצמו כגרסה אפית/טריילרית."""
    haystack = f"{track.get('track', '')} {track.get('album', '')}".lower()
    return any(re.search(rf"\b{re.escape(m)}", haystack) for m in EPIC_TITLE_MARKERS)


# ביטויים שאפל שמה בשם האלבום עצמו כשהגרסה הופקה לסדרה או לסרט. זה שדה
# מטא-דאטה שתמיד חוזר (collectionName), ולכן סימן אמין יותר מהכותרת.
# דוגמה: "The Crown: Season 5 (Soundtrack from the Netflix Series)".
PRODUCTION_ALBUM_MARKERS = (
    r"\bsoundtrack\b",
    r"\bost\b",              # גבול מילה מלא, שלא ייתפס ב-Ghost / Frost / Lost
    r"\bseason\b",
    r"\bseries\b",
    r"\bmotion picture\b",
    r"\boriginal score\b",
    # אפל כותבת 'From "שם ההפקה"' עם מרכאות — זה הדפוס האמיתי.
    # "from the" חשוף תפס גם "Songs From The Bottom", ולכן צומצם.
    r"\bfrom\s+[\"“']",
    r"\bfrom the\s+(film|movie|motion picture|series|show|soundtrack)\b",
    r"\btrailer\b",
    r"\btrailerized\b",
)


def has_production_album(track: dict) -> bool:
    """האם *שם האלבום* מעיד על הפקה לסדרה או לסרט.

    נבדק על האלבום בלבד ולא על שם השיר: שיר שנקרא "Season" או "Series" אינו
    מוזיקה של סדרה, אלבום שנקרא כך כן.
    """
    album = (track.get("album") or "").lower()
    return any(re.search(marker, album) for marker in PRODUCTION_ALBUM_MARKERS)


def is_soundtrack(track: dict) -> bool:
    return any(g in (track.get("genre", "") or "").lower() for g in EPIC_GENRES)


def is_trailer_artist(track: dict) -> bool:
    """אמן או לייבל שידוע בגרסאות טריילר. עובדה על המבצע, לא על הכותרת."""
    artist = (track.get("artist", "") or "").strip()
    if not artist:
        return False
    # `partial_ratio` מחפש את החלון הטוב ביותר, ולכן שם קצר מהזרע מקבל 100
    # על אות אחת מקרית: האמן "X" זכה ל-100 מול "Extreme Music". התאמה חלקית
    # אמורה לתפוס זרע שיושב *בתוך* שם ארוך יותר, ולכן זרע ארוך מהשם נפסל.
    lowered = artist.lower()
    return (any(len(seed) <= len(lowered)
                and fuzz.partial_ratio(seed.lower(), lowered) > 90
                for seed in EPIC_SEEDS)
            or any(fuzz.ratio(seed.lower(), normalize_artist(artist)) > 90
                   for seed in TRAILER_COVER_ARTISTS))


def trailer_indicators(track: dict) -> list[str]:
    """אילו סימנים נמצאו בפועל, להצגה למשתמש במקום תג אטום.

    אותה רשימה מזינה גם את `trailer_strength` שמדרגת: מה שמוצג כסיבה הוא
    מה שקובע את המקום, ולכן אין פער בין התג שהמשתמש רואה לבין הסדר.
    """
    found = []
    if has_epic_title(track):
        found.append("כותרת אפית")
    if is_soundtrack(track):
        found.append("ז'אנר פסקול")
    if has_production_album(track):
        found.append("אלבום של סדרה/סרט")
    if is_trailer_artist(track):
        found.append("אמן טריילרים מוכר")
    return found


# כמה סימנים נחשבים "עדות מלאה". שלושה מתוך ארבעה מספיקים: דרישה לארבעה
# הייתה הופכת את המדד לבינארי כמעט תמיד.
FULL_TRAILER_EVIDENCE = 3.0


def trailer_strength(track: dict) -> float:
    """כמה חזקה העדות שזו גרסת טריילר, 0..1.

    מדד הדירוג הראשי לצד הטעם והמדידה. הוא נספר מ-`trailer_indicators`
    ולא מ-`epic_bonus`: האחרון כולל מילים רחבות כמו "cover" ו-"version"
    שכמעט כל קאבר מקבל, ולכן אינו מבחין בין גרסת טריילר לכל קאבר אחר.
    """
    return min(1.0, len(trailer_indicators(track)) / FULL_TRAILER_EVIDENCE)


def is_trailer_indicator(track: dict) -> bool:
    """סימן שהגרסה הופקה לטריילר, לסדרה או לסרט.

    כותרת אינה מספיקה: הגרסה של "Bittersweet Symphony" שהופקה ל-The Crown
    נקראת פשוט "Bittersweet Symphony" ואין בה אף מילת מפתח. מה שכן יש לה
    הוא ז'אנר Soundtrack — עובדה בשדה מטא-דאטה, ולכן סימן אמין יותר.
    """
    return has_epic_title(track) or is_soundtrack(track) or has_production_album(track)


# מונחים שנשלחים לחנויות רק בכפתור "גרסאות טריילר אפיות". הם רחבים מדי
# לחיפוש רגיל, אבל בדיוק הם שמוציאים גרסאות של סדרות וסרטים.
EPIC_SEARCH_MODIFIERS = (
    "trailerized", "trailer version", "ost", "season", "series", "from the",
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


def normalize_title(title: str) -> str:
    """מנרמל כותרת כך שווריאציות ניסוח של אותו שיר נופלות על אותה מחרוזת.

    נדרש כי "California Dreaming" שהמשתמש מקליד ו-"California Dreamin\'" שהוא השם
    האמיתי הפיקו עד היום מפתחות שונים, וכל שרשרת ההתאמה נשברה בגללם.
    """
    s = (title or "").lower()
    # סמן שיבוץ בפסקול: 'Song - From "Movie"' או 'Song (From "Movie")'
    s = re.sub(r'\s*[-–—]?\s*\(?from\s+["“].*$', "", s)
    # Dreamin' -> Dreaming. מוסיף g רק אחרי אפוסטרוף, לעולם לא מוריד g קיים,
    # ולכן "Sing" ו-"Bring" אינם נפגעים.
    s = re.sub(r"(?<=\w)in'(?=\s|$)", "ing", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_artist(artist: str) -> str:
    s = clean_artist_name(artist).lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def track_key(artist: str, track: str) -> str:
    """מפתח זהות לשיר — הבסיס לניפוי כפילויות בין אלבומים ובין מקורות."""
    return f"{normalize_artist(artist)}|{normalize_title(clean_track_title(track))}"


# ---------- שאילתות ----------

MAX_SPACING_VARIANTS = 3


def spacing_variants(text: str) -> list[str]:
    """כתיב מאוחד מול מופרד: "Bitter Sweet Symphony" מול "Bittersweet Symphony".

    בלי זה הגרסה של The Crown, ששמה מילה אחת, לא הוחזרה כלל מהחנויות כשהוקלד
    הכתיב של The Verve בשתי מילים.
    """
    words = text.split()
    if len(words) < 2:
        return []
    variants = []
    for i in range(len(words) - 1):
        joined = words[:i] + [words[i] + words[i + 1]] + words[i + 2:]
        candidate = " ".join(joined)
        if candidate.lower() != text.lower():
            variants.append(candidate)
    return variants[:MAX_SPACING_VARIANTS]


def build_queries(query: str, filters: dict | None = None,
                  origin_artist: str = "",
                  extra_modifiers: tuple = ()) -> list[str]:
    """בונה כמה וריאציות שאילתה במקום אחת — זה שורש ההרחבה של המאגר."""
    base = (query or "").strip()
    if not base:
        return []

    queries = [base]
    queries += [f"{base} {modifier}" for modifier in EPIC_MODIFIERS]
    queries += [f"{base} {modifier}" for modifier in extra_modifiers]

    # כתיב חלופי, וגם עם "soundtrack" כי שם מתחבאות גרסאות של סדרות
    for variant in spacing_variants(base):
        queries.append(variant)
        queries.append(f"{variant} soundtrack")

    # חיפוש לפי אמן המקור: "cover of <artist>" מוצא גרסאות לשירים שלו
    if origin_artist:
        queries.append(f"{origin_artist} {base}")
        queries.append(f"{origin_artist} cover")
        queries.append(f"{base} {origin_artist} cover")

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

# ---------- שכבת HTTP: כישלון אינו "אין תוצאות" ----------

USER_AGENT = os.environ.get(
    "TRAILER_SONG_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
HTTP_ATTEMPTS = 3
HTTP_BACKOFF = 0.6      # שניות, מוכפל בכל ניסיון
RETRY_STATUSES = (429, 500, 502, 503, 504)

_errors: list[str] = []
_errors_lock = threading.Lock()


def reset_errors():
    with _errors_lock:
        _errors.clear()


def last_errors() -> list[str]:
    with _errors_lock:
        return list(_errors)


def _record_error(message: str):
    with _errors_lock:
        _errors.append(message[:120])


def get_json(url: str, client: httpx.Client | None = None, timeout: float = 10.0,
             headers: dict | None = None, params: dict | None = None):
    """GET עם ניסיונות חוזרים. מחזיר None כשהבקשה נכשלה — ולא dict ריק.

    זו ההבחנה שהחסרה שלה גרמה ל"לא נמצאו תוצאות" על כישלון רשת: חנות שהחזירה
    429 או 503 נראתה בדיוק כמו חיפוש שלא מצא כלום, והלחיצה השנייה "עבדה".
    """
    # User-Agent אמיתי כברירת מחדל: iTunes מחזיר 403 לבקשות עם ה-UA הדיפולטי
    # של httpx, במיוחד מכתובות של דאטה-סנטר. זה לא מעקף חסימה אלא זיהוי תקין —
    # בקשה בלי UA כלל היא מה שנראה חריג
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last = ""
    for attempt in range(HTTP_ATTEMPTS):
        try:
            response = (client or httpx).get(url, timeout=timeout,
                                             headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            last = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUSES:
                break
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
        if attempt < HTTP_ATTEMPTS - 1:
            time.sleep(HTTP_BACKOFF * (attempt + 1))
    _record_error(f"{urllib.parse.urlsplit(url).netloc} — {last}")
    return None


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
        "release_date": (item.get("releaseDate") or "")[:10],
        "year": (item.get("releaseDate") or "")[:4],
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
        "release_date": "",
        "year": "",
    }


def itunes_search(term: str, country: str = "US", limit: int = 200,
                  client: httpx.Client | None = None) -> list[dict]:
    params = {
        "term": term, "media": "music", "entity": "song",
        "limit": min(limit, 200), "country": country,
    }
    url = f"{ITUNES_URL}?{urllib.parse.urlencode(params)}"
    payload = get_json(url, client=client)
    if payload is None:
        return []
    return [t for t in (_normalize_itunes(i) for i in payload.get("results", [])) if t]


def deezer_search(term: str, limit: int = 100,
                  client: httpx.Client | None = None) -> list[dict]:
    url = f"{DEEZER_URL}?{urllib.parse.urlencode({'q': term, 'limit': min(limit, 100)})}"
    payload = get_json(url, client=client)
    if payload is None:
        return []
    return [t for t in (_normalize_deezer(i) for i in payload.get("data", [])) if t]


# ---------- דירוג וניפוי ----------

# תקרה לבונוס ה"אפיות". בלעדיה טראק שמתאים גרוע לשאילתה אבל דחוס במילות מפתח
# ניצח התאמה מדויקת: "California Dreaming (Epic Cinematic Trailer Cover Version)"
# קיבל 140 מול 97 של הגרסה האמיתית של Sia.
MAX_EPIC_BONUS = 30
# מתחת לרצפה הזו טראק לא מוצג בכלל (ראו השימוש ב-search_covers) ולא רק
# מדורג נמוך. מכויל מול: קאברים לגיטימיים (אחרי ניקוי תג גרסה) מגיעים
# ל-100; "At Long Last, Love" מול שאילתת "At Last" — שיר אחר לגמרי שחולק
# שתי מילים — מגיע ל-60; "Yellow Submarine" מול "Yellow" ל-57.
RELEVANCE_FLOOR = 65


def relevance(track: dict, query: str, match_artist: bool = False) -> int:
    """כמה השיר תואם למה שהמשתמש חיפש, על מחרוזות מנורמלות.

    `match_artist` מרשה לשם האמן לענות במקום הכותרת, ונדרש רק כשהשאילתה
    *היא* אמן או ז'אנר ("עוד באותו סגנון"). כשהשאילתה היא שם שיר זו הייתה
    תקלה: `token_set_ratio("happy", "demob happy")` הוא 100, ולכן חיפוש
    "Happy" החזיר את כל הקטלוג של להקות ששמן מכיל את המילה — "Demob Happy
    — Hades, Baby" קיבל בדיוק את אותו ציון כמו "Pharrell Williams — Happy".

    `fuzz.token_set_ratio` לבד מחזיר 100 לכל כותרת שמכילה את *כל* מילות
    השאילתה כתת-קבוצה — "At Long Last, Love" מקבל 100 מול שאילתת "At Last"
    בדיוק כמו התאמה מדויקת, כי הוא לא מבחין בין "אותו שיר עם תוספת" ל"שיר
    אחר לגמרי שחולק שתי מילים". `fuzz.ratio` על מחרוזות מרוכזות רגיש לאורך
    ומעניש מילים זרות בכותרת המועמד; לוקחים min של שניהם. הכותרת מנוקה
    קודם מתגיות גרסה (`clean_track_title`) כדי שקאבר אפי לגיטימי לא יפסיד
    בהשוואת אורך רק בגלל "(Epic Trailer Version)" שהוא עצמו מחפש.
    """
    if not query:
        return 100
    q = normalize_title(query)
    raw_title = track.get("track", "")
    title = normalize_title(clean_track_title(raw_title) or raw_title)
    # השוואה נוספת בלי רווחים, שההבדל בין "bitter sweet" ל-"bittersweet"
    # לא יוריד את הציון של הגרסה הנכונה
    squeeze = lambda s: s.replace(" ", "")
    title_score = min(
        fuzz.token_set_ratio(q, title),
        fuzz.ratio(squeeze(q), squeeze(title)),
    )
    if not match_artist:
        return title_score
    return max(
        title_score,
        fuzz.token_set_ratio(q, normalize_artist(track.get("artist", ""))),
    )


def epic_bonus(track: dict) -> int:
    """בונוס על סימני 'קאבר אפי'. כל סימן נספר פעם אחת, והסכום חסום."""
    artist = track.get("artist", "")
    haystack = f"{artist} {track.get('track', '')} {track.get('album', '')}".lower()

    bonus = 0
    if any(kw in haystack for kw in EPIC_KEYWORDS):
        bonus += 8
    if any(g in (track.get("genre", "") or "").lower() for g in EPIC_GENRES):
        # ז'אנר פסקול על *קאבר* לשיר מוכר הוא הסימן החזק ביותר שיש במטא-דאטה
        # לגרסה שהופקה לסדרה או לסרט. זו עובדה בשדה, לא מילה בכותרת.
        bonus += 20
    if has_production_album(track):
        # שם האלבום שאפל נותנת בפועל: "... Season 5 (Soundtrack from the
        # Netflix Series)". תופס גם כשהז'אנר לא סומן Soundtrack.
        bonus += 20
    if is_trailer_artist(track):
        bonus += 15
    return min(bonus, MAX_EPIC_BONUS)


def release_year(track: dict) -> int:
    """שנת יציאה כמספר, או 0 כשלא ידועה."""
    raw = str(track.get("year") or track.get("release_date") or "")[:4]
    return int(raw) if raw.isdigit() else 0


def freshness_bonus(track: dict, now_year: int | None = None) -> int:
    """בונוס לחומר חדש. יורד מ-25 לאפס על פני חמש שנים."""
    year = release_year(track)
    if not year:
        return 0
    now_year = now_year or _dt.date.today().year
    age = now_year - year
    if age < 0:
        return 0
    return int(round(max(0.0, 25 * (1 - age / 5))))


def score_track(track: dict, query: str, prefer_new: bool = False,
                match_artist: bool = False) -> int:
    """רלוונטיות ראשית, אפיות כתוספת חסומה — לא להפך.

    prefer_new מוסיף בונוס טריות, כך ש"חדש עם ציון גבוה" עולה מעל ישן עם אותו ציון.
    """
    score = relevance(track, query, match_artist=match_artist) + epic_bonus(track)
    if prefer_new:
        score += freshness_bonus(track)
    if not track.get("preview_url"):
        score -= 25  # אי אפשר להאזין — פחות שימושי
    return int(score)


def passes_length_filter(duration_sec: float, length_filter: str | None) -> bool:
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
                  include_seeds: bool = True, origin_artist: str = "",
                  prefer_new: bool = False, min_year: int = 0,
                  extra_modifiers: tuple = (),
                  match_artist: bool = False) -> list[dict]:
    """מחזיר מאגר קאברים ממוין לפי רלוונטיות, ללא כפילויות.

    exclude_keys — שירים שהמשתמש כבר ראה, כדי שחיפוש חוזר יביא חומר חדש.
    """
    queries = build_queries(query, filters, origin_artist, extra_modifiers)
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
        if not passes_length_filter(track.get("duration_sec", 0), (filters or {}).get("length")):
            continue
        if track_key(track.get("artist", ""), track.get("track", "")) in exclude_keys:
            continue
        if min_year and release_year(track) and release_year(track) < min_year:
            continue
        # מתחת לרצפת הרלוונטיות זה כנראה שיר אחר לגמרי שחולק כמה מילים עם
        # השאילתה ("At Long Last, Love" מול "At Last") — לא מדורג נמוך,
        # לא מוצג בכלל.
        if relevance(track, query, match_artist=match_artist) < RELEVANCE_FLOOR:
            continue
        track["score"] = score_track(track, query, prefer_new=prefer_new,
                                     match_artist=match_artist)
        scored.append(track)

    unique = dedupe(scored)
    unique.sort(key=lambda t: t.get("score", 0), reverse=True)
    return unique
