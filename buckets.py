"""חלוקת התוצאות לקטגוריות: לאיזה *סוג* גרסה כל קאבר שייך.

רשימה שטוחה של שישים קאברים לאותו שיר היא רשימה שצריך לקרוא עד הסוף.
החלוקה כאן עונה על השאלה שבאמת נשאלת מול תוצאות של חיפוש קאברים —
"תראה לי את גרסאות הרוק", "יש בכלל אקפלה?" — בלי לחפש מחדש.

**קטגוריה אחת לכל קאבר**, לפי `ORDER`. גרסה שמופיעה בכמה מקומות גורמת
לסכום הקטגוריות להיות גדול ממספר התוצאות, וזה קורא כמו כפילות.

## על מה כל קטגוריה נשענת, ומה זה אומר על הכיסוי

- **כותרת/אלבום** (אקפלה, אינסטרומנטלי, טריילר): עובד לשתי החנויות, כי
  הטקסט תמיד מגיע. תופס רק את מי ש*מצהיר* על עצמו.
- **ז'אנר** (קלאסי, רוק, טראנס): מגיע מ-iTunes בלבד —
  `search.py` מחזיר `"genre": ""` לכל תוצאה מ-Deezer. לכן לכל
  קטגוריה כזו יש גם סימני כותרת, אחרת חצי מהתוצאות היו נופלות בשקט
  לקטגוריית השארית.
- **מדידה** (רגוע): מגיעה מהדפדפן שניות אחרי שהתוצאות כבר על המסך, ולכן
  שורה יכולה לעבור מ"כל השאר" ל"רגוע" תוך כדי. ראו את ההערה ב-`group`.
"""
from __future__ import annotations

import re

import search as search_module
import tags

ALL = "All"

ACAPPELLA = "A cappella"
TRAILER = "Trailer / epic"
INSTRUMENTAL = "Instrumental"
CLASSICAL = "Classical"
ROCK = "Rock"
TRANCE = "Trance / electronic"
CALM = "Calm"
OTHER = "Everything else"

# סדר העדיפויות **וגם** סדר התצוגה. קאבר נכנס לראשונה שמתאימה לו, ולכן
# שינוי סדר כאן משנה את החלוקה — זו הידית היחידה שצריך לגעת בה.
#
# אקפלה ראשונה כי היא הנדירה והמוצהרת ביותר: גרסה שכתוב עליה שהיא
# אקפלה היא קודם כל אקפלה. אחריה טריילר, כי זה מה שהאפליקציה הזו
# מחפשת מלכתחילה.
ORDER = (ACAPPELLA, TRAILER, INSTRUMENTAL, CLASSICAL, ROCK, TRANCE, CALM, OTHER)

_TITLE_MARKERS = {
    ACAPPELLA: ("a cappella", "acappella", "a-cappella", "vocals only",
                "vocal only", "voice only"),
    INSTRUMENTAL: ("instrumental", "karaoke", "backing track", "no vocals",
                   "playback", "minus one"),
    CLASSICAL: ("orchestra", "orchestral", "symphony", "symphonic", "philharmonic",
                "string quartet", "strings", "cello", "violin", "piano solo",
                "solo piano", "chamber", "opera"),
    ROCK: ("rock", "metal", "punk", "grunge", "guitar", "hardcore", "riff"),
    TRANCE: ("trance", "remix", "edm", "dubstep", "house mix", "club mix",
             "techno", "electro", "dance mix", "bootleg"),
}

_GENRE_MARKERS = {
    CLASSICAL: ("classical", "opera", "chamber"),
    ROCK: ("rock", "metal", "punk", "grunge"),
    TRANCE: ("dance", "electronic", "electronica", "house", "techno", "trance", "edm"),
    INSTRUMENTAL: ("instrumental",),
}


def _haystack(track: dict) -> str:
    return f"{track.get('track', '')} {track.get('album', '')}".lower()


def _hits(text: str, markers: "tuple[str, ...]") -> bool:
    """גבול מילה **משני הצדדים**, ולא `in`.

    `search.has_epic_title` מעגן רק את ההתחלה (`\bepic`), וזה מספיק שם כי
    הסמנים שלו ארוכים וייחודיים. כאן זה לא הספיק ונמדד: `\brock` תופס את
    **Rocket Man**, כי "Rocket" מתחיל בגבול מילה. העיגון בסוף הוא מה שמפריד
    בין "Rock Cover" לבין "Rocket Man" — ולכן שתי הצורות קיימות בקוד הזה
    בכוונה, ולא מתוך חוסר עקביות.
    """
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers)


def _is_trailer(track: dict) -> bool:
    """עדות טריילר מהכותרת, מהאלבום ומהאמן — **בלי הז'אנר**.

    `search.trailer_indicators` סופר גם `is_soundtrack`, ו-`EPIC_GENRES`
    כולל "classical" ו-"instrumental". שימוש בו כאן היה בולע את שתי
    הקטגוריות האלה לתוך "טריילר" ומשאיר אותן ריקות לנצח — כלומר החלוקה
    הייתה נראית עובדת ובעצם מסתירה בדיוק את מה שביקשו לראות.
    """
    return (search_module.has_epic_title(track)
            or search_module.has_production_album(track)
            or search_module.is_trailer_artist(track))


def _is_calm(features: "dict | None") -> bool:
    """רגוע = איטי **או** שקט, ובלבד שאינו קצבי.

    נשען על `tags.py` ולא על ספים חדשים: SLOW_BURN ו-INTIMATE הן שתיים
    מהתגיות שנשענות על `audio.WEIGHTS`, שטווחיו כוילו מול מדידות אמיתיות
    (בניגוד למדדי הגוון). סף חדש כאן היה מספר קסם שלישי לאותו דבר.
    """
    found = tags.tags_for(features)
    if not found:
        return False
    if tags.ACTION in found or tags.RELENTLESS in found:
        return False
    return tags.SLOW_BURN in found or tags.INTIMATE in found


def bucket_of(track: dict, features: "dict | None" = None) -> str:
    """הקטגוריה היחידה של קאבר אחד."""
    text, genre = _haystack(track), (track.get("genre") or "").lower()

    def declared(name: str) -> bool:
        return (_hits(text, _TITLE_MARKERS.get(name, ()))
                or _hits(genre, _GENRE_MARKERS.get(name, ())))

    for name in ORDER:
        if name == OTHER:
            break
        if name == TRAILER:
            if _is_trailer(track):
                return TRAILER
        elif name == CALM:
            if _is_calm(features):
                return CALM
        elif declared(name):
            return name
    return OTHER


def group(tracks: list, measurements: "dict | None" = None) -> "list[tuple[str, list]]":
    """(שם קטגוריה, שורות) לפי `ORDER`, בלי קטגוריות ריקות.

    הסדר בתוך כל קטגוריה הוא הסדר שהתקבל — כלומר המיון שכבר הוחל
    ב-`ordered_display` נשמר, והחלוקה לא מסדרת מחדש שום דבר.

    **הקבוצה מחושבת מחדש בכל ריצה, וזה מכוון.** המדידה מגיעה מהדפדפן
    אחרי שהתוצאות כבר על המסך, ולכן שורה יכולה לעבור פעם אחת מ"כל השאר"
    ל"רגוע" כשהמדידה שלה נוחתת. הקטגוריות עצמן לא זזות (הסדר קבוע
    ב-`ORDER`), ולכן זו השלמה של מדף ולא ערבוב מחדש של הרשימה.
    """
    measurements = measurements or {}
    found: dict = {}
    for track in tracks:
        name = bucket_of(track, measurements.get(track.get("uid")))
        found.setdefault(name, []).append(track)
    return [(name, found[name]) for name in ORDER if found.get(name)]


def counts(tracks: list, measurements: "dict | None" = None) -> dict:
    """כמה קאברים בכל קטגוריה. הבסיס לשורת הכפתורים שמעל התוצאות.

    נספר על **כל** התוצאות ולא על העמוד המוצג, אחרת המספר על הכפתור היה
    אומר "כמה מזה במקרה נטען" במקום "כמה יש".
    """
    measurements = measurements or {}
    tally: dict = {}
    for track in tracks:
        name = bucket_of(track, measurements.get(track.get("uid")))
        tally[name] = tally.get(name, 0) + 1
    return tally
