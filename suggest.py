"""השלמת שמות שירים ותיקון שגיאות כתיב, מול קטלוג אמיתי.

שתי תקלות הקלט שמבזבזות חיפוש:

1. **שגיאת כתיב או שם חלקי.** "bitter sweet symphany" או "bitter sweet symph"
   מחזירים מעט מאוד, והמשתמש לא יודע אם השיר לא קיים או שהוא פשוט טעה.
2. **פריסת מקלדת עברית.** הקלדת שם באנגלית כשהמקלדת בעברית מייצרת ג'יבריש
   ("איממקר" במקום "winter"). זו תקלה דטרמיניסטית וניתנת להיפוך בדיוק מלא.

התיקון לא מנחש מילון: ההצעות הן שמות שירים אמיתיים שחזרו מ-iTunes, כך שהצעה
תמיד מצביעה על משהו שקיים במאגר שבו נחפש בפועל.
"""
from thefuzz import fuzz

import search as search_module
from search import normalize_title

# פריסת המקלדת הישראלית: לכל אות עברית האות האנגלית שיושבת על אותו מקש
HE_TO_EN = {
    "/": "q", "'": "w", "ק": "e", "ר": "r", "א": "t", "ט": "y", "ו": "u",
    "ן": "i", "ם": "o", "פ": "p",
    "ש": "a", "ד": "s", "ג": "d", "כ": "f", "ע": "g", "י": "h", "ח": "j",
    "ל": "k", "ך": "l", "ף": ";",
    "ז": "z", "ס": "x", "ב": "c", "ה": "v", "נ": "b", "מ": "n", "צ": "m",
    "ת": ",", "ץ": ".",
}

SUGGEST_LIMIT = 8          # כמה הצעות להביא לתצוגה
FETCH_LIMIT = 25           # כמה תוצאות למשוך מ-iTunes לפני הסינון
MIN_QUERY_LEN = 3          # מתחת לזה כל דבר דומה לכל דבר
CORRECTION_FLOOR = 65      # מתחת לזה זה שיר אחר, לא תיקון
EXACT_ENOUGH = 96          # מעל זה הקלט כבר נכון ואין מה לתקן


def has_hebrew(text: str) -> bool:
    return any("֐" <= char <= "ת" for char in text)


def fix_layout(text: str) -> str:
    """הופך הקלדה עברית בטעות לאנגלית. אותיות שאינן עבריות נשארות כמות שהן."""
    return "".join(HE_TO_EN.get(char, char) for char in text)


def _label(track: dict) -> str:
    year = track.get("year")
    return (f"{track['track']} — {track['artist']}"
            + (f" ({year})" if year else ""))


def _rank(track: dict, query: str) -> int:
    """כמה ההצעה קרובה למה שהוקלד. partial_ratio תופס שם חלקי."""
    title = normalize_title(track.get("track", ""))
    target = normalize_title(query)
    return max(fuzz.ratio(title, target), fuzz.partial_ratio(title, target))


def _fetch(term: str) -> list[dict]:
    return search_module.itunes_search(term, limit=FETCH_LIMIT)


def suggest(query: str, limit: int = SUGGEST_LIMIT) -> list[dict]:
    """שמות שירים אמיתיים שמתאימים למה שהוקלד, הכי קרוב קודם.

    כשהקלט נראה כמו הקלדה בפריסה עברית, מנסים גם את הגרסה המתוקנת ובוחרים
    את הצד שהחזיר התאמה טובה יותר — במקום להחליט מראש מה המשתמש התכוון.
    """
    query = (query or "").strip()
    if len(query) < MIN_QUERY_LEN:
        return []

    terms = [query]
    swapped = fix_layout(query)
    if has_hebrew(query) and swapped != query:
        terms.append(swapped)

    best: dict[str, dict] = {}
    for term in terms:
        for track in _fetch(term):
            key = f"{normalize_title(track['track'])}|{track['artist'].lower()}"
            score = _rank(track, term)
            if score > best.get(key, {}).get("match", -1):
                best[key] = {
                    "track": track["track"],
                    "artist": track["artist"],
                    "year": track.get("year", ""),
                    "match": score,
                    "label": _label(track),
                }

    ranked = sorted(best.values(), key=lambda item: item["match"], reverse=True)
    return ranked[:limit]


def did_you_mean(query: str, suggestions: list[dict] | None = None) -> dict | None:
    """ההצעה היחידה שכדאי להציע כתיקון, או None כשהקלט כבר תקין.

    מוחזר רק כשההצעה קרובה מספיק כדי להיות אותו שיר (מעל הרצפה) ורחוקה מספיק
    כדי להיות תיקון בכלל (מתחת ל"זהה"). בלי זה היינו מציעים למשתמש את מה
    שהוא כבר הקליד.
    """
    query = (query or "").strip()
    if len(query) < MIN_QUERY_LEN:
        return None
    if suggestions is None:
        suggestions = suggest(query)
    if not suggestions:
        return None

    top = suggestions[0]
    if top["match"] >= EXACT_ENOUGH or top["match"] < CORRECTION_FLOOR:
        return None
    if normalize_title(top["track"]) == normalize_title(query):
        return None
    return top
