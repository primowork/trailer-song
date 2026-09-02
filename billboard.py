"""ייבוא מצעדי בילבורד מעמוד שנשמר, במקום גרידה חיה.

למה לא למשוך ישירות מ-billboard.com: אין להם API ציבורי, הגרידה נוגדת את תנאי
השימוש שלהם, והם חוסמים IP-ים של דאטה-סנטרים — בדיוק הכשל של ifpi.co.il, שבו
פיצ'ר "עובד אצלי" ונופל בדיפלוימנט. לא הצלחתי אפילו לבדוק את זה מהסביבה הזאת.

מה שכן עובד: המשתמש שומר עמוד מצעד מהדפדפן שלו ומעלה אותו, והפרסר כאן הופך אותו
לרשימה מדורגת. אותו מבנה HTML משרת את כל המצעדים — Hot 100, Billboard 200,
Greatest of All Time — ולכן פרסר אחד מכסה את כולם.
"""
import re

from bs4 import BeautifulSoup

ROW_SELECTOR = "div.o-chart-results-list-row-container"
TITLE_SELECTOR = "h3#title-of-a-story"
LABEL_SELECTOR = "span.c-label"

SONGS = "songs"
ARTISTS = "artists"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_chart(html: str) -> dict:
    """מחזיר {'title', 'kind', 'entries'} מעמוד מצעד שמור. לא זורק חריגות.

    בשורת מצעד יש דירוג (ה-c-label הראשון), כותרת (h3) והשדה שאחריה. במצעד שירים
    השדה הזה הוא האמן; במצעד אמנים הוא חוזר על שם האמן, וזה מה שמבדיל ביניהם.
    """
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return {"title": "", "kind": SONGS, "entries": []}

    page_title = _clean(soup.title.get_text() if soup.title else "")

    entries = []
    for row in soup.select(ROW_SELECTOR):
        heading = row.select_one(TITLE_SELECTOR)
        if not heading:
            continue
        primary = _clean(heading.get_text())
        if not primary:
            continue

        sibling = heading.find_next_sibling()
        secondary = _clean(sibling.get_text()) if sibling else ""

        labels = [_clean(label.get_text()) for label in row.select(LABEL_SELECTOR)]
        rank = next((int(label) for label in labels if label.isdigit()), len(entries) + 1)

        entries.append({"rank": rank, "primary": primary, "secondary": secondary})

    if not entries:
        return {"title": page_title, "kind": SONGS, "entries": []}

    # מצעד אמנים: השדה השני חוזר על הראשון (או חסר). ההשוואה מתעלמת מרישיות
    # ובודקת רוב ולא הכל — בדף האמיתי שורה אחת מתוך 125 כתובה "JAY-Z" מול "Jay-Z",
    # ו-all() קיצוני מדי כדי לשרוד דף אמיתי.
    same = sum(1 for e in entries
               if not e["secondary"] or e["secondary"].casefold() == e["primary"].casefold())
    artist_chart = same >= len(entries) * 0.8

    shaped = []
    for entry in entries:
        if artist_chart:
            shaped.append({"rank": entry["rank"], "artist": entry["primary"], "track": ""})
        else:
            shaped.append({"rank": entry["rank"], "artist": entry["secondary"],
                           "track": entry["primary"]})

    shaped.sort(key=lambda item: item["rank"])
    return {"title": page_title, "kind": ARTISTS if artist_chart else SONGS,
            "entries": shaped}


def chart_slug(title: str) -> str:
    """מזהה קובץ יציב לשם המצעד, כדי שייבוא חוזר יעדכן ולא ישכפל."""
    slug = re.sub(r"[^\w]+", "-", (title or "chart").lower()).strip("-")
    return slug[:60] or "chart"
