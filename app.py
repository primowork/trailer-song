"""ממשק Streamlit: גילוי גרסאות קאבר אפיות לטריילרים."""
import csv
import os
import datetime as _dt
import html
import io
import random
import time

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

import httpx
import streamlit as st
import streamlit.components.v1 as components

import accounts
import artists as artists_module
import audio
import billboard as billboard_module
import buckets
import classics as classics_module
import covers as covers_module
import youtube as youtube_module
import preview as preview_module
import storage
import search as search_module
import tags as tags_module
import taste
from search import (ALL, LENGTH_LONG, LENGTH_MEDIUM, LENGTH_SHORT, STYLES,
                    clean_artist_name, search_covers, track_key)

PAGE_SIZE = 20
# אפשרויות המיון. קבועים ולא מחרוזות מוטבעות: הן גם תוויות תצוגה וגם
# הענפים ב-`sorted_by`, ומחרוזת שהוקלדה פעמיים במקומות רחוקים היא בדיוק
# איך שמיון מפסיק לעבוד בלי שאף אחד שם לב.
SORT_BEST = "Best match"
SORT_LOUDNESS = "Loudness (measured)"
SORT_RELEVANCE = "Relevance"
SORT_NEWEST = "Newest first"
SORT_SHORTEST = "Shortest first"
SORT_LONGEST = "Longest first"
SORT_ARTIST = "Artist"
SORT_OPTIONS = (SORT_BEST, SORT_LOUDNESS, SORT_RELEVANCE, SORT_NEWEST,
                SORT_SHORTEST, SORT_LONGEST, SORT_ARTIST)

# שלושת מצבי החיפוש. "Covers of a song" ממזג שני מקורות (מאגר יחסי + חיפוש
# בחנויות) תחת בחירה אחת — הם עונים בפועל על אותה שאלה. "Covers of an artist"
# ו-"Free search" הם כוונות שונות באמת (קלט שונה; חיפוש רחב מכוון-פילטרים)
# ונשארים מצבים נפרדים.
# מתחת לזה התג "מתאים לטעם שלך" הוא רעש: עם מעט לייקים כל הטראקים מקבלים
# ציון נמוך דומה, ותג על כולם אינו אומר דבר
TASTE_BADGE_THRESHOLD = 0.35

MODE_SONG = "Covers of a song"
MODE_ARTIST = "Covers of an artist"
MODE_FREE = "Free search"
SEARCH_MODES = [MODE_SONG, MODE_ARTIST, MODE_FREE]

# פילטר "חדשות": התווית וסף השנה שהיא מייצגת. 0 = בלי סינון.
RECENCY_OPTIONS = {
    "Any year": 0,
    "Past year": _dt.date.today().year,
    "Past 2 years": _dt.date.today().year - 1,
    "Past 5 years": _dt.date.today().year - 4,
}

# מקורות אינדקס המצעדים. קבועים ולא מחרוזות מוטבעות, כי הם גם ערכי widget
# (`index_source` ב-session_state) וגם תוויות תצוגה.
SOURCE_CLASSICS = "Classics"
SOURCE_GOAT = "Billboard: greatest artists"

st.set_page_config(page_title="COVER LOVER", page_icon="\U0001F3B5", layout="wide")

# כל שפת החזות של האפליקציה, במקום אחד. הערכים מגיעים מטבלת הטוקנים
# ב-`design_handoff_cover_lover/README.md` (כיוון 1a — STUDIO) והם ערכי
# כוונה סופיים; מה שאין לו טוקן מסומן כאן בהערה למה נבחר.
#
# `max-width` על אזור התוכן: ב-`layout="wide"` הטופס נמתח על פני 1400px
# ומפזר את העין. הרוחב הרחב עדיין משרת את הרשתות (אינדקס המצעדים).
#
# הערה על מה שנמחק כאן: עד לגרסה הזו הבלוק החזיק כללי RTL (כיווניות על
# אזור התוכן ועל הסרגל בנפרד, יישור לימין, ו-`unicode-bidi: plaintext`
# שמנע חיתוך שם לטיני בתוך שורה עברית). הממשק עבר לאנגלית ו-LTR, ולכן
# **כולם ירדו** — כולל העקיפה של הבאג שבו `direction: rtl` על השורש הפך
# את ה-`translateX` השלילי שבו Streamlit מקפל את הסרגל בטלפון. הבאג ההוא
# לא קיים ב-LTR; אין כאן טלאי שהוסר בלי תחליף.
st.markdown(
    """
    <style>
    /* הגופנים נטענים כאן ולא ב-config.toml: ה-theme מקבל שם משפחה, לא
       כתובת. שלוש משפחות, כל אחת בתפקיד אחד — ראו את ההערה ב-config.

       **מהפרויקט עצמו ולא מ-Google Fonts.** הגרסה הראשונה עשתה
       `@import` מ-fonts.googleapis.com, ובפריסה בפועל זה נכשל: הבקשה
       לגיליון הסגנונות יצאה, אבל **אף קובץ גופן לא ירד** (אפס בקשות
       ל-fonts.gstatic.com) — וכל הממשק נפל לגופן ברירת המחדל של
       המערכת. גופן שהוא חלק מהזהות אינו יכול להיות תלוי בכך שרשת
       חיצונית תענה לדפדפן של המשתמש.

       הקובץ (תת-קבוצת latin, 38KB) יושב ב-`static/fonts/` ומוגש על ידי
       Streamlit עצמו — `enableStaticServing` ב-config. Nunito הוא גופן
       משתנה, ולכן טווח 400–800 מכסה בקובץ אחד את כל המשקלים שבשימוש:
       גוף ב-400, כותרות שורה ב-600, ומספרים ותגים ב-800.

       קודם ישבו כאן שלוש משפחות (91KB יחד). המשתמש ביקש משפחה עגולה
       אחת לכל דבר, ולכן זה גם 53KB פחות לרדת. */
    @font-face {
        font-family: 'Nunito';
        src: url('app/static/fonts/nunito.woff2') format('woff2');
        font-weight: 400 800; font-style: normal; font-display: swap;
    }

    :root {
        --ink: #0A0B0F;
        --rail: #101219;
        --surface: #14161D;
        --raised: #161A24;
        --chip: #1E2230;
        --chip-on: #252A38;
        --line: #1E2230;
        --line-strong: #232838;
        --line-row: #2A3040;
        --nav-on: #1A1E29;
        --text: #ECEEF3;
        --text-2: #C3C8D4;
        --text-3: #8A91A3;
        --text-4: #9AA1B2;
        --text-5: #7B839A;
        --amber: #FFB020;
        --coral: #FF6B4A;
        /* משפחה אחת, ושתי הרמות שהיא צריכה לכסות. `ui-rounded` לפני
           `system-ui` נותן ל-macOS ול-iOS את SF Pro Rounded כשהגופן
           עוד לא נטען, כלומר הנפילה לאחור היא לגופן עגול ולא לגופן
           אחר לגמרי. */
        --sans: 'Nunito', ui-rounded, system-ui, sans-serif;
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1180px;
        /* 26px כמו בעיצוב, ולא ריפוד ברירת המחדל של Streamlit: הוא לקח
           כ-100px מרוחב השורה, וזה בדיוק הרוחב שחסר לה */
        padding-inline: 26px;
        padding-top: 1.4rem;
        /* מקום לסרגל הנגן, שהוא `position: fixed` ולכן אינו תופס גובה
           בזרימה. בלי זה השורה האחרונה יושבת מתחתיו ואי אפשר להגיע אליה */
        padding-bottom: 96px;
    }

    /* מספרים בטבלה אחת: ציון 87 ו-ציון 9 חייבים להתחיל באותו מקום, אחרת
       העין קופצת בין השורות */
    [data-testid="stMain"] { font-variant-numeric: tabular-nums; }

    /* אלמנט האודיו וסרגל הנגן יוצאים מהזרימה (מוסתר / `position: fixed`),
       אבל מכולת ה-`st.html` שלהם עדיין תפסה גובה בראש העמוד ודחפה את
       שורת החיפוש מטה. נמדד בדפדפן.
       גובה אפס ולא `display: none`: הסתרת המכולה מוציאה גם את הילדים
       מעץ הרינדור — הסרגל יצא 0x0 ולא הופיע כלל (נמדד), ואלמנט מדיה
       שהוצא מהעץ הוא מקור ידוע לסירובי נגינה ב-Safari לנייד. */
    .stElementContainer:has(> .stHtml > #ts-bar),
    .stElementContainer:has(> .stHtml > audio) {
        height: 0; min-height: 0; margin: 0; padding: 0; overflow: visible;
    }

    /* טקסט משני אמיתי ולא אפור-על-אפור: היררכיה במקום שש שורות זהות */
    [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: var(--text-3);
        font-size: 12.5px;
        line-height: 1.5;
    }
    /* הצבע עצמו מגיע מ-`linkColor` ב-theme (חל על כל הרכיבים); כאן רק
       המעבר, שהוא מה שמסמן שהטקסט לחיץ בלי אקסנט על כל שורה */
    [data-testid="stMain"] a:hover { color: var(--amber) !important; }

    /* ---- ה-rail ---- */
    [data-testid="stSidebar"] {
        background: var(--rail);
        border-inline-end: 1px solid var(--line);
        width: 210px !important; min-width: 210px !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding: 18px 14px;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.34rem; }

    .ts-brand { display: flex; align-items: center; gap: 9px; margin-bottom: 16px; }
    /* סמל: ריבוע ענבר עם חור כהה — תקליט, לא ריבוע מלא */
    .ts-mark {
        width: 22px; height: 22px; border-radius: 6px; background: var(--amber);
        position: relative; flex: none;
    }
    .ts-mark::after {
        content: ""; position: absolute; inset: 8px;
        border-radius: 50%; background: var(--ink);
    }
    .ts-word {
        font-family: var(--sans); font-weight: 800; font-size: 13px;
        letter-spacing: .14em; line-height: 1.15; color: var(--text);
    }

    /* פריט ניווט. הפעיל מזוהה לפי סיומת ה-key (`nav_<item>_on`) — ראו
       `_rail_nav`: אין ל-Streamlit דרך לתת class למכולה. */
    [class*="st-key-nav_"] { border-radius: 8px; padding: 0 2px; }
    [class*="st-key-nav_"][class*="_on"] { background: var(--nav-on); }
    [class*="st-key-nav_"] .stButton button {
        min-height: 34px; padding: 0 8px; border: none; background: transparent;
        color: var(--text-3); font-size: 13.5px; font-weight: 400;
        justify-content: flex-start;
    }
    [class*="st-key-nav_"][class*="_on"] .stButton button {
        color: var(--text); font-weight: 500;
    }
    [class*="st-key-nav_"] .stButton button:hover { color: var(--text); }
    /* המונה הוא המספר היחיד ב-rail, ולכן mono וענבר */
    .ts-navcount {
        font-family: var(--sans); font-weight: 500; font-size: 11px;
        color: var(--amber); white-space: nowrap;
    }

    .ts-railrule { height: 1px; background: var(--line); margin: 14px 0 4px; }
    /* דוחף את RECENT לתחתית ה-rail, כמו בעיצוב */
    .ts-railfill { flex: 1 1 auto; min-height: 12px; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(> .stElementContainer .ts-railfill) {
        min-height: calc(100vh - 120px);
    }
    /* תוויות micro ב-mono: הן שלטי חלוקה, לא כותרות — ולכן קטנות,
       מרווחות ובאותיות גדולות, ולא עוד שורת טקסט בגודל הגוף */
    .ts-railcap {
        font-family: var(--sans); font-weight: 500; font-size: 10px;
        letter-spacing: .12em; color: var(--text-4);
        margin: 10px 0 8px; text-transform: uppercase;
    }
    .ts-railtaste {
        margin: 0; font-size: 12px; line-height: 1.55; color: var(--text-3);
    }
    .ts-railrecent {
        font-size: 12.5px; color: var(--text-2); padding: 2px 0;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }

    /* הפלייליסט ב-rail: שורות טקסט, לא תשעה מלבנים. המסגרת היחידה
       שנשארת היא של כפתור הנגינה. */
    [data-testid="stSidebar"] .stButton button {
        min-height: 32px; padding: 0 0.35rem;
    }
    [data-testid="stSidebar"] .stButton button,
    [data-testid="stSidebar"] .stButton button > div {
        justify-content: flex-start; text-align: start; width: 100%;
    }
    [data-testid="stSidebar"] .stButton button p {
        font-size: 12.5px; overflow: hidden;
        text-overflow: ellipsis; white-space: nowrap;
    }
    [data-testid="stSidebar"] details summary { font-size: 12.5px; }

    /* ---- סרגל עליון: טלפון בלבד ---- */
    /* בדסקטופ ה-rail כבר נושא את הזהות ואת המונה, ולכן כפילות. בטלפון
       ה-rail מקופל מאחורי כפתור ההמבורגר ואין על המסך שום זהות. */
    .st-key-appbar { gap: 0.55rem; margin-bottom: 0.75rem; display: none; }
    .ts-word-inline { letter-spacing: .16em; font-size: 12.5px; }

    /* ---- שורת החיפוש ---- */
    /* המסגרת שייכת למכולה, והשדות שקופים בתוכה — כך כל הפקדים נקראים
       כרכיב אחד ולא כארבעה טפסים נפרדים */
    .st-key-searchbar {
        border: 1px solid var(--line-strong); border-radius: 12px;
        background: var(--surface); padding: 6px 6px 6px 14px; gap: 10px;
    }
    .st-key-searchbar [data-baseweb="input"],
    .st-key-searchbar [data-baseweb="base-input"],
    .st-key-searchbar [data-testid="stTextInputRootElement"] {
        border: none !important; background: transparent !important;
    }
    .st-key-searchbar input { font-size: 15px; }
    .st-key-searchbar [data-testid="stElementContainer"]:has(input) {
        flex-grow: 1; min-width: 120px;
    }
    /* מכולת הזכוכית לא גדלה. ברירת המחדל של Streamlit למכולת אלמנט
       בתוך מכולה אופקית היא `flex: 1 1 fit-content`, ולכן היא נמתחה על
       כל רוחב השורה ודחפה את שדה השיר לשורה משלו — ארבע שורות בטלפון
       במקום שתיים (נמדד). */
    .st-key-searchbar [data-testid="stElementContainer"]:has(.ts-searchglyph) {
        /* רוחב מפורש ולא `auto`: מכולת ה-`st.html` היא בלוק, ולכן
           `flex-basis: auto` נותן לה 100% מהשורה גם כשהתוכן הוא
           גליף של 13px. אותה תקלה בדיוק כמו בנגן (`.ts-player`). */
        flex: 0 0 16px; width: 16px;
    }
    /* זכוכית מגדלת מצוירת ב-CSS ולא ב-SVG: Streamlit מסנן <svg> מתוך
       st.html, ואייקון מוטמע פשוט לא מגיע לדף (נמדד בדפדפן) */
    .ts-searchglyph {
        width: 13px; height: 13px; flex: none; border-radius: 50%;
        border: 1.6px solid var(--text-4); position: relative;
        display: inline-block; margin-inline-end: 1px;
    }
    .ts-searchglyph::after {
        content: ""; position: absolute; width: 1.6px; height: 6px;
        background: var(--text-4); transform: rotate(-45deg);
        inset-inline-start: 12px; top: 10px; border-radius: 1px;
    }
    /* השדה מוסתר כשה-chip נושא את הערך. ראו את ההערה ב-`app.py`: הוא
       עדיין **נוצר**, אחרת Streamlit מנקה את המפתח ושם האמן אובד. */
    .st-key-searchbar:has(.ts-chiptext) .st-key-cover_artist {
        display: none !important;
    }
    /* האמן כ-chip: mono, כי הוא ערך שנקבע ולא טקסט חופשי */
    .st-key-artistchip {
        border: 1px solid var(--line-strong); border-radius: 5px;
        padding: 1px 3px 1px 7px; gap: 2px; flex: none;
    }
    .ts-chiptext {
        font-family: var(--sans); font-weight: 500; font-size: 11px;
        color: var(--text-4); white-space: nowrap;
    }
    .st-key-clear_artist button { min-height: 22px; padding: 0 2px; }
    /* Surprise me — כפתור ghost; Find covers — ענבר מלא */
    .st-key-btn_dice button {
        border: 1px solid var(--line-strong); background: transparent;
        color: var(--text-2); border-radius: 8px; height: 32px;
        min-height: 32px; padding: 0 10px; font-size: 13px; white-space: nowrap;
    }
    .st-key-btn_dice button:hover { color: var(--text); border-color: #2E3547; }
    .st-key-btn_search button {
        border: none; background: var(--amber); color: var(--ink);
        border-radius: 8px; height: 32px; min-height: 32px; padding: 0 16px;
        font-weight: 600; font-size: 13.5px; white-space: nowrap;
    }
    .st-key-btn_search button:hover { background: #FFC65C; color: var(--ink); }
    .st-key-btn_search button p { font-weight: 600; }

    /* ---- שורת המצבים ---- */
    .st-key-moderow { gap: 8px; margin-top: 12px; }
    /* מעטפת segmented: הקבוצה כולה היא פקד אחד עם מסגרת אחת, והפעיל
       הוא לשונית בתוכה — ולא שלושה כפתורים שמתחרים על תשומת לב */
    .st-key-moderow [data-testid="stButtonGroup"] {
        background: var(--surface); border: 1px solid var(--line-strong);
        border-radius: 9px; padding: 3px; gap: 0;
    }
    .st-key-moderow [data-testid="stButtonGroup"] button {
        border: none !important; background: transparent !important;
        border-radius: 6px !important; padding: 5px 11px !important;
        min-height: 28px; color: var(--text-3) !important; font-size: 12.5px;
    }
    .st-key-moderow [data-testid="stButtonGroup"] button[aria-checked="true"],
    .st-key-moderow [data-testid="stButtonGroup"] button[aria-pressed="true"] {
        background: var(--chip-on) !important; color: var(--text) !important;
        font-weight: 500;
    }
    .ts-sortlabel { font-size: 12.5px; color: var(--text-3); white-space: nowrap; }
    .st-key-moderow [data-testid="stSelectbox"] { min-width: 150px; }
    .st-key-moderow [data-baseweb="select"] > div {
        background: transparent; border-color: var(--line-strong);
        border-radius: 8px; min-height: 30px; font-size: 12.5px;
    }
    .st-key-moderow [data-testid="stPopover"] button {
        background: transparent; border: 1px solid var(--line-strong);
        border-radius: 8px; min-height: 30px; padding: 0 10px;
        color: var(--text-3); font-size: 12.5px;
    }
    .ts-filtercount {
        font-family: var(--sans); font-weight: 500; font-size: 11px;
        color: var(--amber); margin-inline-start: -4px;
    }

    /* פקדי משנה שקטים: הם תחזוקה של התצוגה, לא פעולה ראשית, ולכן בלי
       מסגרת ובגודל הטקסט המשני */
    .st-key-resortrow .stButton button,
    .st-key-btn_which button {
        border: none; background: transparent; color: var(--text-3);
        min-height: 26px; padding: 0; font-size: 12.5px;
    }
    .st-key-resortrow .stButton button:hover:not(:disabled),
    .st-key-btn_which button:hover { color: var(--amber); }
    .st-key-resortrow { margin: -2px 0 10px; }
    .st-key-btn_which { margin-top: 2px; }

    /* ---- מסך הפתיחה ---- */
    /* כותרת קטגוריה בין קבוצות התוצאות. מרווח עליון גדול מהתחתון:
       הכותרת שייכת למה שמתחתיה, וריווח סימטרי היה גורם לה להיראות
       כשייכת לשורה שמעליה. */
    .ts-groupcap {
        display: flex; align-items: center; gap: 8px;
        margin: 22px 0 8px;
    }
    .ts-groupcap:first-child { margin-top: 6px; }
    .ts-startcap { margin: 18px 0 10px; }
    /* נקודות ההתחלה נראות כמו שורות תוצאה ולא ככפתורים גנריים: זו אותה
       פעולה (לחיצה מריצה חיפוש), ולכן אותה שפה */
    [class*="st-key-start_"] button {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 10px; min-height: 52px; padding: 0 14px;
        color: var(--text-2);
    }
    /* גם ה-div הפנימי, לא רק הכפתור: בלעדיו התווית יושבת במרכז השורה
       ולא בתחילתה (אותו כלל בדיוק נדרש בשורות הפלייליסט) */
    [class*="st-key-start_"] button,
    [class*="st-key-start_"] button > div {
        justify-content: flex-start; text-align: start; width: 100%;
    }
    [class*="st-key-start_"] button:hover {
        background: var(--raised); border-color: var(--line-row);
        color: var(--text);
    }
    [class*="st-key-start_"] button p {
        font-size: 13.5px; overflow: hidden;
        text-overflow: ellipsis; white-space: nowrap;
    }

    /* ---- מסך הפלייליסט ---- */
    /* קבוצה לכל שיר מקור. בעמודה הראשית יש לה את הרוחב לנשום, ולכן
       הכותרת נקראת בשורה אחת במקום להישבר לשלוש (מה שקרה כשהמסך הזה
       ישב ב-rail של 210px). */
    [class*="st-key-lovedgroup_"] [data-testid="stExpander"] details {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 10px;
    }
    [class*="st-key-lovedgroup_"] summary { font-size: 14px; font-weight: 500; }
    /* שורת גרסה שמורה: אותה שפה כמו שורת תוצאה — נגן, שם, והסרה.
       היישור לשמאל מוגדר כאן ולא דרך `[data-testid="stSidebar"]`: כשהמסך
       ישב בסרגל הוא ירש אותו משם, ובמעבר לעמודה הראשית כל שם אמן קפץ
       למרכז של 984px (נמדד). */
    [class*="st-key-favrow_"] {
        gap: 10px; padding: 4px 6px; border-radius: 8px;
    }
    [class*="st-key-favrow_"]:hover { background: var(--raised); }
    [class*="st-key-favrow_"] .stButton button {
        border: none; background: transparent; min-height: 34px;
        padding: 0 4px; color: var(--text-2);
    }
    [class*="st-key-favrow_"] .stButton button:hover { color: var(--text); }
    [class*="st-key-favrow_"] .stButton button,
    [class*="st-key-favrow_"] .stButton button > div {
        justify-content: flex-start; text-align: start;
    }
    [class*="st-key-favrow_"] .stButton button p {
        font-size: 13.5px; overflow: hidden;
        text-overflow: ellipsis; white-space: nowrap;
    }
    /* כפתור ההסרה נשאר ברוחב האייקון שלו ואינו נמתח על השורה */
    [class*="st-key-favrow_"] [class*="st-key-unfav_"] button {
        width: 32px; min-width: 32px; padding: 0;
    }
    .st-key-lovedactions { gap: 10px; margin: 0 0 14px; }
    .st-key-lovedactions .stButton button,
    .st-key-lovedactions [data-testid="stDownloadButton"] button {
        border: 1px solid var(--line-strong); background: transparent;
        color: var(--text-2); border-radius: 8px;
        min-height: 32px; padding: 0 12px; font-size: 13px;
    }

    /* ---- כותרת התוצאות ---- */
    .ts-resulthead {
        display: flex; align-items: baseline; gap: 10px;
        flex-wrap: wrap; margin: 22px 0 8px;
    }
    .ts-h2 {
        font-family: var(--sans); font-weight: 800; font-size: 28px;
        letter-spacing: -.025em; margin: 0; color: var(--text);
    }
    .ts-lede { font-size: 13.5px; font-weight: 600; color: var(--text-3); }

    /* ---- שורת תוצאה ---- */
    /* כרטיס ולא שורה צרה: פינה של 18px וריפוד נדיב, מהרפרנס שהמשתמש
       הביא. הקו הוא `inset box-shadow` ולא `border`, כדי שלא יוסיף
       פיקסל לגובה השורה ולא יזיז את הפריסה שנמדדה בדפדפן. */
    [class*="st-key-trow_"] {
        background: var(--surface); box-shadow: inset 0 0 0 1px var(--line);
        border-radius: 18px; padding: 13px 16px; margin-bottom: 10px;
    }
    [class*="st-key-trow_"]:has(.ts-play.is-playing) {
        background: var(--raised); box-shadow: inset 0 0 0 2px var(--amber);
    }
    [class*="st-key-trow_"] [data-testid="stVerticalBlock"] { gap: 0; }
    /* בלוק הכותרת הוא היחיד שגדל ומתכווץ; שאר העמודות ברוחב התוכן שלהן.
       בלי `min-width: 0` שם האמן לא נחתך ב-ellipsis אלא **דוחף** את
       העמודות שאחריו, ובלי `flex` הוא נכווץ עד "T.." (נמדד בדפדפן). */
    /* ה-`st-key-` יושב על המכולה הפנימית, בעוד שפריט ה-flex הוא
       **העוטף** שלה (נמדד בדפדפן: העוטף הוא זה שקיבל `flex: 1 1 128px`).
       לכן כל כלל פריסה כאן נתפס דרך `:has()` על העוטף — כלל שנכתב על
       המחלקה עצמה פשוט לא משפיע על הפריסה. */
    [class*="st-key-trow_"] > div:has(> [class*="st-key-tmain_"]) {
        flex: 1 1 auto !important; min-width: 120px !important;
    }
    /* התגים אינם מתכווצים: תג חתוך באמצע מילה ("SOUNE") גרוע מתג
       שאינו מוצג. מה שכן מתכווץ הוא המד, שיש לו רצפה משלו. */
    [class*="st-key-trow_"] > div:has(> [class*="st-key-ttags_"]) {
        flex: 0 0 auto !important;
    }
    [class*="st-key-trow_"] > div:has(> [class*="st-key-tmeter_"]) {
        flex: 0 1 auto !important; min-width: 0 !important;
    }
    [class*="st-key-trow_"] > div:has(> [class*="st-key-tacts_"]) {
        flex: 0 0 auto !important;
    }
    .ts-rowartist {
        font-size: 14.5px; font-weight: 600; line-height: 1.3; color: var(--text);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .ts-rowmeta {
        font-size: 12.5px; line-height: 1.4; color: var(--text-3); margin-top: 2px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .ts-rowmeta a { color: var(--text-2); text-decoration: none; }
    .ts-rowmeta a:hover { color: var(--amber); }
    /* תגי הסימנים: מילוי רך במקום מתאר, מהרפרנס. המילוי הוא ענבר
       בעשירית האטימות ולא ענבר מלא — הם הסיבה לדירוג ולא קישוט, וריבוע
       ענבר מלא על כל שורה היה מבטל את המשמעות של הענבר. */
    .ts-tags { display: flex; gap: 6px; flex-wrap: nowrap; }
    .ts-tag {
        font-family: var(--sans); font-weight: 800; font-size: 11px;
        letter-spacing: .05em; color: var(--amber);
        background: rgba(255,176,32,.13); border-radius: 8px;
        padding: 5px 9px; white-space: nowrap;
    }
    /* התג הנמדד: אותה צורה בדיוק, בלי הענבר. ההבדל בין "מה שהוכרז" לבין
       "מה שנשמע" הוא הבדל במקור ולא בחשיבות, ולכן הוא נקרא בצבע ולא
       בגודל או במיקום. */
    .ts-tag-heard {
        color: #A8AEBE;
        background: var(--chip);
    }

    /* מד העוצמה: אורך קבוע, ולכן אפשר להשוות שורה לשורה במבט אחד.
       `max-width` ורצפה על הרצועה: ברוחב צר הוא מתכווץ עד 70px ואז
       עוצר, במקום להיעלם או לדחוס את שם האמן. */
    /* המספר מעל הרצועה ובגודל שקוראים אותו מיד, מהרפרנס. הרצועה
       נשארת מתחתיו כי היא מה שמאפשר להשוות שורה לשורה במבט אחד —
       המספר עונה על "כמה", הרצועה על "לעומת מי". */
    .ts-meter {
        display: flex; flex-direction: column; align-items: flex-end;
        gap: 5px; width: 92px; max-width: 100%;
    }
    .ts-metertrack {
        width: 100%; height: 6px; border-radius: 3px;
        background: var(--chip); overflow: hidden;
    }
    .ts-meterfill { height: 100%; border-radius: 3px; }
    /* גובה קבוע לשתי המצבים: שורה שנמדדה מציגה מספר של 27px ושורה שלא
       מציגה תווית של 11px, ובלי הגובה הזה הרשימה הייתה קופצת בכל פעם
       שמדידה מסתיימת. */
    .ts-meterval {
        font-family: var(--sans); font-weight: 800; font-size: 27px;
        line-height: 28px; height: 28px; letter-spacing: -.02em;
        text-align: end; flex: none;
    }
    .ts-meteridle {
        color: var(--text-5); font-size: 11px; font-weight: 700;
        letter-spacing: .06em; line-height: 28px; height: 28px;
    }
    .ts-fit {
        font-family: var(--sans); font-size: 10px; color: var(--text-5);
        margin-top: 5px; text-align: end;
    }

    /* פעולות השורה: לב, לא-זה, ותפריט */
    [class*="st-key-tacts_"] { gap: 6px; }
    [class*="st-key-tacts_"] .stButton button,
    [class*="st-key-tacts_"] [data-testid="stPopover"] button {
        width: 32px; min-width: 32px; height: 32px; min-height: 32px;
        padding: 0; border-radius: 8px; border: 1px solid var(--line-strong);
        background: transparent; color: var(--text-4);
    }
    [class*="st-key-tacts_"] .stButton button:hover { color: var(--text); }
    /* הערה: ל-popover של Streamlit יש חץ קטן אחרי ה-"⋯". ניסיתי להסתיר
       אותו ולא הצלחתי בלי להסתיר גם את ה-⋯ עצמו (שני האייקונים אינם
       אחים באותה רמה), ולכן הוא נשאר — הוא גם לא שקר: הכפתור באמת פותח
       תפריט. אין כאן כלל CSS מת שמתיימר לטפל בזה. */
    /* לב אהוב: אלמוג. זה האקסנט השני והיחיד, והוא שמור לפעולה הזו בלבד */
    [class*="st-key-tacts_"] .stButton button[kind="primary"] {
        background: rgba(255,107,74,.12); border-color: rgba(255,107,74,.45);
        color: var(--coral);
    }

    /* עטיפה חסרה: גרדיאנט וגליף במקום ריבוע אפור שטוח שמושך את העין */
    .ts-art-blank {
        border-radius: 13px; border: 1px solid var(--line-strong);
        background: repeating-linear-gradient(135deg,#1B1F2A 0 6px,#161A24 6px 12px);
        flex: none;
    }
    [class*="st-key-trow_"] [data-testid="stImage"] img { border-radius: 13px; }

    /* ---- נגן ---- */
    /* נגן ה-<audio controls> של הדפדפן יושב ב-shadow DOM שלא ניתן לעיצוב,
       ולכן הוא הגיע בפלטה של הדפדפן ולא של האפליקציה. כאן ה-<audio>
       נשאר אבל מוסתר, ומעליו כפתור נגינה אחד בלבד — תצוגה מקדימה של
       שלושים שניות לא צריכה פס התקדמות. */
    .ts-player { display: flex; align-items: center; width: 34px; flex: none; }
    .stElementContainer:has(> .stHtml .ts-player) { flex: 0 0 34px; width: 34px; }
    /* לא display:none: אלמנט מדיה שהוצא מעץ הרינדור הוא מקור ידוע לסירובי
       נגינה ב-Safari לנייד. מוסתר בלי לצאת מהעץ. */
    .ts-player audio {
        position: absolute; width: 1px; height: 1px;
        opacity: 0; pointer-events: none;
    }
    /* המשולש והמקפים מצוירים ב-CSS ולא ב-SVG: ראו הערת הזכוכית המגדלת */
    .ts-play {
        width: 44px; height: 44px; flex: none; border: none; cursor: pointer;
        border-radius: 50%; background: var(--chip);
        display: flex; align-items: center; justify-content: center; padding: 0;
    }
    .ts-play::before {
        content: ""; width: 0; height: 0; border-style: solid;
        border-width: 6px 0 6px 10px;
        border-color: transparent transparent transparent var(--text);
        margin-inline-start: 2px;
    }
    .ts-play:hover { background: #262C3B; }
    .ts-play.is-playing { background: var(--amber); }
    .ts-play.is-playing::before {
        width: 9px; height: 11px; border: none; margin: 0;
        background: linear-gradient(90deg, var(--ink) 0 3px, transparent 3px 6px,
                                    var(--ink) 6px 9px);
    }
    /* תצוגה מקדימה שאינה נטענת: כפתור מושתק במקום כפתור שנראה תקין
       ולא עושה דבר */
    .ts-play.is-dead { background: var(--chip); cursor: not-allowed; }
    .ts-play.is-dead::before {
        border-color: transparent transparent transparent #5A6274;
        background: none; width: 0; height: 0;
        border-width: 6px 0 6px 10px; border-style: solid;
    }
    /* מקום שמור לכפתור שאין לו מה לנגן, כדי שהשורות יישארו על אותו קו */
    .ts-noplay {
        height: 34px; width: 34px; border-radius: 50%;
        border: 1px dashed var(--line-strong);
    }

    /* כפתור ההעתקה בשורות הפלייליסט. האייקון מצויר ב-CSS ולא באימוג'י
       ולא ב-Material: שתי הדרכים האלה כבר נכשלו כאן ברינדור (כפתור
       הקובייה יצא נקודה כתומה בשני סבבים), ושני ריבועים חופפים הם בדיוק
       מה שאפשר לצייר בלי תלות בגופן כלשהו. */
    .ts-copy {
        position: relative; flex: none;
        height: 32px; width: 32px; padding: 0;
        background: transparent; border: none; cursor: pointer;
        border-radius: 8px; color: var(--text-3);
    }
    .ts-copy::before, .ts-copy::after {
        content: ""; position: absolute; border: 1.4px solid currentColor;
        border-radius: 3px; width: 11px; height: 13px;
    }
    /* הגיליון האחורי מוסט למעלה-שמאלה, הקדמי למטה-ימינה */
    .ts-copy::before { top: 7px; left: 8px; opacity: .55; }
    .ts-copy::after { top: 11px; left: 12px; background: var(--surface); }
    .ts-copy:hover { color: var(--text); background: var(--chip); }
    /* המכולה של `st.html` מקבלת מ-Streamlit `flex: 1 1 fit-content` ובולעת
       את המקום שנשאר בשורה — נמדד בדפדפן 371px למכולה של כפתור 32px, ולכן
       האייקון צף באמצע השורה ומשנה מקום לפי אורך שם האמן במקום להתיישר
       בעמודה. הכלל חייב לתפוס את **העוטף** דרך `:has()`, כי `st-key-`
       יושב על המכולה הפנימית ולא על פריט ה-flex. */
    .stElementContainer:has(> .stHtml > .ts-copy) {
        flex: 0 0 32px;
        width: 32px;
    }
    /* משוב שהעתקה קרתה בפועל. אין כאן rerun ולכן אין דרך אחרת לדעת. */
    .ts-copy.is-copied { color: var(--amber); }

    /* ---- סרגל הנגן התחתון ---- */
    .ts-bar {
        position: fixed; inset-inline: 0; bottom: 0; z-index: 90;
        display: flex; align-items: center; gap: 14px;
        padding: 12px 26px; background: var(--rail);
        border-top: 1px solid var(--line);
    }
    @media (min-width: 768px) { .ts-bar { inset-inline-start: 210px; } }
    .ts-bar-art {
        width: 40px; height: 40px; flex: none; border-radius: 7px;
        border: 1px solid var(--line-strong); background-size: cover;
        background-position: center;
    }
    .ts-bar-art.is-blank {
        background: repeating-linear-gradient(135deg,#1B1F2A 0 6px,#161A24 6px 12px);
    }
    .ts-bar-text { min-width: 0; flex: 1; }
    .ts-bar-title {
        font-size: 13.5px; font-weight: 600; color: var(--text);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .ts-bar-sub { font-size: 12px; color: var(--text-3); }
    .ts-bar-sub a { color: var(--text-3); }
    .ts-bar-sub a:hover { color: var(--amber); }
    .ts-bar-keys {
        font-family: var(--sans); font-weight: 500; font-size: 11px;
        color: var(--text-4); white-space: nowrap; flex: none;
    }
    /* האקווילייזר. `is-live` נדלק רק כששמע באמת מתנגן (ראו `paint`) —
       פסים שרוקדים על שמע עצור הם תנועה בלי מקור. */
    .ts-eq {
        display: flex; gap: 2px; align-items: flex-end;
        height: 22px; width: 34px; flex: none;
    }
    .ts-eq i { flex: 1; background: var(--amber); height: 100%;
               transform-origin: bottom; transform: scaleY(.35); }
    .ts-bar.is-live .ts-eq i { animation: ts-eqbar .9s ease-in-out infinite; }
    .ts-bar.is-live .ts-eq i:nth-child(2) { animation-delay: .15s; }
    .ts-bar.is-live .ts-eq i:nth-child(3) { animation-delay: .3s; }
    .ts-bar.is-live .ts-eq i:nth-child(4) { animation-delay: .45s; }
    @keyframes ts-eqbar {
        0%, 100% { transform: scaleY(.35); }
        50% { transform: scaleY(1); }
    }
    /* מי שהעדיף פחות תנועה מקבל סרגל סטטי, לא סרגל חסר */
    @media (prefers-reduced-motion: reduce) {
        .ts-bar.is-live .ts-eq i { animation: none; transform: scaleY(.7); }
    }

    /* ---- טלפון ---- */
    @media (max-width: 767px) {
        [data-testid="stMainBlockContainer"] {
            padding: 0.9rem 0.9rem 5.5rem;
        }
        .st-key-appbar { display: flex; }
        .ts-h2 { font-size: 20px; }
        .ts-resulthead { margin: 16px 0 6px; gap: 6px; }

        /* שורת החיפוש: הזכוכית והשדה בשורה אחת, והכפתורים יורדים מתחת.
           `flex-basis: 100%` על השדה דחף את הזכוכית לשורה משלה (נמדד). */
        /* בלי `order` בכלל: סדר ה-DOM כבר נכון (זכוכית, שיר, אמן,
           הגרלה, חיפוש), ומה ששבר אותו קודם היה `flex-basis: 100%` על
           השדה — שדחף את הזכוכית לשורה משלה. */
        /* שורה ראשונה: זכוכית + שם השיר יחד. שדה האמן יורד לשורה משלו,
           והכפתורים מתחתיו.
           `flex-basis: 100%` על **כל** שדה דחף גם את הזכוכית לשורה
           נפרדת ועשה מזה ארבע שורות (נמדד). הבסיס הגמיש הוא על שדה
           השיר, וה-100% רק על שדה האמן. */
        .st-key-searchbar { padding: 10px 13px; gap: 8px 9px; }
        .st-key-searchbar .st-key-cover_title {
            /* בסיס 0 ולא `auto`: הרוחב הטבעי של שדה הטקסט גדול מהמקום
               שנשאר ליד הזכוכית, ולכן `auto` הפיל אותו לשורה משלו */
            flex: 1 1 0; min-width: 0;
        }
        .st-key-searchbar .st-key-cover_artist {
            flex: 1 1 100%; min-width: 0;
        }
        .st-key-btn_dice button, .st-key-btn_search button {
            height: 34px; min-height: 34px;
        }

        /* מצבי החיפוש נגללים אופקית במקום להיערם לשלוש שורות. `!important`
           כי ה-flex-wrap מגיע מהרכיב עצמו ולא מהמכולה שלנו. */
        .st-key-moderow [data-testid="stButtonGroup"],
        .st-key-moderow [data-testid="stButtonGroup"] > div {
            flex-wrap: nowrap !important; overflow-x: auto; max-width: 100%;
            scrollbar-width: none;
        }
        .st-key-moderow [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) {
            max-width: 100%; overflow: hidden;
        }
        .st-key-moderow [data-testid="stButtonGroup"]::-webkit-scrollbar {
            display: none;
        }

        /* שורת הקטגוריות מקבלת בדיוק את אותו טיפול, ומאותה סיבה: נמדד
           ב-390px שהיא נערמת ל-**שלוש שורות ו-104px**, שנדחפות מעל
           התוצאות — כלומר בדיוק מה שהעיצוב ביקש למנוע במצבי החיפוש. */
        .st-key-kindrow [data-testid="stButtonGroup"],
        .st-key-kindrow [data-testid="stButtonGroup"] > div {
            flex-wrap: nowrap !important; overflow-x: auto; max-width: 100%;
            scrollbar-width: none;
        }
        .st-key-kindrow [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) {
            max-width: 100%; overflow: hidden;
        }
        .st-key-kindrow [data-testid="stButtonGroup"]::-webkit-scrollbar {
            display: none;
        }
        /* בלי אלה הגלולות **מתכווצות** במקום להיגלל: נמדד ב-390px שהן
           ירדו ל-34-50px כל אחת, כלומר תווית כמו "Trance / electronic"
           נדחסת עד שאי אפשר לקרוא אותה. */
        .st-key-kindrow [data-testid="stButtonGroup"] button {
            white-space: nowrap; flex: none;
        }
        /* גלולות עגולות **נפרדות**, ולא קופסה אחת עם מסגרת: זה מה
           שהעיצוב מגדיר לטלפון. */
        .st-key-moderow [data-testid="stButtonGroup"],
        .st-key-moderow [data-testid="stButtonGroup"] > div {
            background: transparent; border: none; padding: 0; gap: 6px;
        }
        .st-key-moderow [data-testid="stButtonGroup"] button {
            white-space: nowrap; flex: none;
            border: 1px solid var(--line-strong) !important;
            border-radius: 20px !important; padding: 6px 11px !important;
            min-height: 32px;
        }
        .st-key-moderow [data-testid="stButtonGroup"] button[aria-checked="true"],
        .st-key-moderow [data-testid="stButtonGroup"] button[aria-pressed="true"] {
            border-color: transparent !important;
        }
        .st-key-moderow { gap: 8px 10px; }
        .st-key-moderow [data-testid="stSelectbox"] { min-width: 130px; }

        /* השורה בטלפון היא **רשת** ולא flex, כדי לקבל את הצורה שבעיצוב:
           העטיפה גבוהה לגובה שתי השורות, הכותרת והמד זה מעל זה לצידה,
           והכפתורים בבלוק מימין.
           `display: contents` על מכולת הפעולות הוא מה שמאפשר את זה:
           בלעדיו שלושת הכפתורים הם תא **אחד** ברוחב 148px שאינו נכנס
           לצד המד; איתו כל כפתור הוא פריט רשת בפני עצמו שאפשר למקם. */
        [class*="st-key-trow_"] {
            display: grid !important;
            grid-template-columns: 52px minmax(0, 1fr) 44px 44px;
            grid-template-rows: auto auto;
            gap: 8px 10px !important; align-items: center;
            padding: 11px; border-radius: 12px;
        }
        [class*="st-key-trow_"] > div:first-child {
            grid-column: 1; grid-row: 1 / span 2; align-self: start;
        }
        [class*="st-key-trow_"] > div:has(> [class*="st-key-tmain_"]) {
            grid-column: 2; grid-row: 1; min-width: 0;
        }
        [class*="st-key-trow_"] > div:has(> [class*="st-key-tmeter_"]) {
            grid-column: 2; grid-row: 2; min-width: 0;
        }
        [class*="st-key-trow_"] .ts-meter { width: 100%; }
        /* בטלפון אין תגים בשורה גם בעיצוב עצמו: ברוחב 390px הם דחסו את
           שם האמן לשליש מהרוחב, וזו בדיוק התלונה שהם אמורים לשרת */
        [class*="st-key-trow_"] > div:has(> [class*="st-key-ttags_"]) {
            display: none !important;
        }
        [class*="st-key-trow_"] > div:has(> [class*="st-key-tplay_"]) {
            grid-column: 3; grid-row: 1;
        }
        [class*="st-key-trow_"] > div:has(> [class*="st-key-tacts_"]),
        [class*="st-key-tacts_"] { display: contents !important; }
        /* לב ליד הנגינה, ומתחתיהם "לא זה" ו-⋯: ארבעה יעדי 44px בבלוק
           אחד, במקום שורה שנייה שמתחרה עם המד על הרוחב */
        [class*="st-key-tacts_"] > div:nth-child(1) { grid-column: 4; grid-row: 1; }
        [class*="st-key-tacts_"] > div:nth-child(2) { grid-column: 3; grid-row: 2; }
        [class*="st-key-tacts_"] > div:nth-child(3) { grid-column: 4; grid-row: 2; }
        [class*="st-key-tacts_"] .stButton button,
        [class*="st-key-tacts_"] [data-testid="stPopover"] button {
            width: 44px; min-width: 44px; height: 44px; min-height: 44px;
        }

        .ts-play, .ts-noplay { width: 44px; height: 44px; }
        .ts-player { width: 44px; }
        .stElementContainer:has(> .stHtml .ts-player) {
            flex: 0 0 44px; width: 44px;
        }
        .ts-art-blank { border-radius: 13px; }

        /* רמזי המקלדת אינם רלוונטיים בלי מקלדת, והם גזלו את הרוחב מהשם */
        .ts-bar-keys { display: none; }
        .ts-bar { padding: 11px 16px; gap: 11px; }
        .ts-eq { width: 26px; height: 18px; }
        .ts-eq i:nth-child(4) { display: none; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# אלמנט האודיו היחיד בדף, לפני כל כפתור נגינה שמצביע אליו
st.html("<audio id='ts-audio' preload='none'></audio>")

# סרגל הנגן. מרונדר **פעם אחת** וריק, והדפדפן ממלא אותו (ראו
# `_audio_behaviour`). סרגל שהיה נבנה בפייתון היה נדרש ל-rerun בכל
# לחיצת נגינה — ובסביבה שבה כל לחיצה ממילא מריצה מחדש את כל הסקריפט,
# זה אומר סרגל שמהבהב בכל פעולה אחרת בדף.
st.html("""
<div id='ts-bar' class='ts-bar' hidden>
  <div class='ts-bar-art'></div>
  <div class='ts-eq'><i></i><i></i><i></i><i></i></div>
  <div class='ts-bar-text'>
    <div class='ts-bar-title'></div>
    <div class='ts-bar-sub'>30-second preview ·
      <a class='ts-bar-link' target='_blank' rel='noopener'>full version on
      YouTube Music &#8599;</a></div>
  </div>
  <div class='ts-bar-keys'>SPACE play · &#8593;&#8595; move · L love</div>
</div>
""")



def _audio_behaviour():
    """מפעיל את כפתורי הנגינה מול אלמנט אודיו אחד משותף.

    **אלמנט אחד ולא אחד לכל שורה.** Safari לנייד מגביל כמה אלמנטי מדיה
    ידע לטעון בדף אחד; פלייליסט של שבעים גרסאות ייצר שבעים אלמנטים, ומעבר
    לתקרה הם פשוט לא נטענים — ומכיוון שהפלייליסט ממוין מהחדש לישן, מה
    שהפסיק לנגן היה בדיוק הישן. נגן משותף גם מייתר את הלוגיקה של "רק אחד
    מנגן בכל רגע": אין מה לעצור.

    delegation על ה-document ולא binding לכל כפתור: הכרטיסים נבנים מחדש
    בכל rerun (וב-Streamlit כל לחיצה היא rerun), וה-iframe הזה אינו מורכב
    מחדש כשה-srcdoc זהה — כלומר סקריפט שרץ פעם אחת בכניסה לא ימצא אף כפתור
    שנוצר אחריו. זה בדיוק הכשל שנמדד קודם בשומר הגלילה.

    הסקריפט מוזרק ל-realm של הדף ולא רץ מתוך ה-iframe: ב-Safari לנייד
    ההרשאה לנגן מדיה נשענת על "מחווה של המשתמש", והיא נבדקת מול ההקשר
    שממנו נקראה `play()`. קריאה מתוך iframe מוצלב-מקור ומסונן היא בדיוק
    המקרה שנחסם.
    """
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__audioBehaviourBound) return;
            doc.__audioBehaviourBound = true;

            const code = function () {
                // חיפוש עצל ולא פעם אחת בכניסה: הסקריפט מוזרק מוקדם, ואילו
                // האלמנט נולד עם שאר העץ של Streamlit
                const media = function () { return document.getElementById("ts-audio"); };

                // הזהות היא data-id ולא הכתובת: הכפתורים נבנים מחדש בכל
                // rerun, ולכן אי אפשר לשמור הפניה לאלמנט; ושתי גרסאות
                // יכולות לחלוק כתובת תצוגה מקדימה
                const paint = function () {
                    const audio = media();
                    const live = audio && !audio.paused && audio.currentSrc;
                    document.querySelectorAll(".ts-play").forEach(function (button) {
                        button.classList.toggle("is-playing",
                            !!(live && button.dataset.id === audio.dataset.playing));
                    });
                    const box = bar();
                    if (!box) return;
                    // האקווילייזר רץ רק כשבאמת מנגן. אנימציה שממשיכה על
                    // שמע שנעצר היא בדיוק סוג הפרט שגורם לממשק להרגיש
                    // מזויף — הוא מראה תנועה שאין לה מקור.
                    box.classList.toggle("is-live", !!live);
                    // הכפתור נבנה מחדש בכל rerun, ולכן הסרגל מתמלא שוב
                    // כאן ולא רק בלחיצה: אחרת לייק באמצע האזנה היה מרוקן
                    // את השם מהסרגל בזמן שהשמע ממשיך לרוץ
                    const button = current();
                    if (button) fill(button);
                };

                // מילוי סרגל הנגן מתוך ה-data-* שעל הכפתור עצמו. אין
                // כאן שום פנייה לפייתון: הכפתור נושא את מה שצריך להציג,
                // ולכן הסרגל מתעדכן באותו frame של הלחיצה.
                const bar = function () { return document.getElementById("ts-bar"); };

                const fill = function (button) {
                    const box = bar();
                    if (!box || !button) return;
                    const art = box.querySelector(".ts-bar-art");
                    const image = button.dataset.art;
                    art.style.backgroundImage = image ? "url(" + image + ")" : "";
                    art.classList.toggle("is-blank", !image);
                    box.querySelector(".ts-bar-title").textContent =
                        (button.dataset.artist || "") +
                        (button.dataset.track ? " \u00b7 " + button.dataset.track : "");
                    const link = box.querySelector(".ts-bar-link");
                    if (button.dataset.url) link.href = button.dataset.url;
                    box.hidden = false;
                };

                // הכפתור שמנגן כרגע, או null. נגזר מה-DOM ולא נשמר
                // במשתנה: הכפתורים נבנים מחדש בכל rerun, והפניה שמורה
                // הייתה מצביעה על אלמנט שכבר לא בעץ.
                const current = function () {
                    const audio = media();
                    if (!audio || !audio.dataset.playing) return null;
                    return document.querySelector(
                        '.ts-play[data-id="' + CSS.escape(audio.dataset.playing) + '"]');
                };

                document.addEventListener("click", function (event) {
                    const button = event.target.closest(".ts-play");
                    if (!button || !button.dataset.src) return;
                    const audio = media();
                    if (!audio) return;
                    if (audio.dataset.playing === button.dataset.id) {
                        audio.paused ? audio.play() : audio.pause();
                        return;
                    }
                    audio.dataset.playing = button.dataset.id;
                    audio.src = button.dataset.src;
                    audio.play();
                    fill(button);
                }, true);

                // העתקה. `navigator.clipboard` דורש הקשר מאובטח (https,
                // וגם localhost) — ולכן יש נפילה לאחור: כישלון שקט כאן
                // הוא כפתור שנראה עובד ואינו מעתיק דבר.
                const flash = function (button) {
                    button.classList.add("is-copied");
                    setTimeout(function () {
                        button.classList.remove("is-copied");
                    }, 1200);
                };

                const legacyCopy = function (text) {
                    const pad = document.createElement("textarea");
                    pad.value = text;
                    pad.setAttribute("readonly", "");
                    pad.style.position = "fixed";
                    pad.style.opacity = "0";
                    document.body.appendChild(pad);
                    pad.select();
                    let ok = false;
                    try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
                    document.body.removeChild(pad);
                    return ok;
                };

                document.addEventListener("click", function (event) {
                    const button = event.target.closest(".ts-copy");
                    if (!button) return;
                    const text = button.dataset.copy || "";
                    if (!text) return;
                    event.preventDefault();
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(text).then(
                            function () { flash(button); },
                            function () { if (legacyCopy(text)) flash(button); });
                        return;
                    }
                    if (legacyCopy(text)) flash(button);
                }, true);

                // מקלדת. SPACE ו-↑↓ נשארים בדפדפן בלבד; L לוחץ על כפתור
                // הלב של השורה, וזה כן מפעיל rerun — מקובל, כי לייק ממילא
                // נכתב לדיסק ומשנה את הדירוג.
                const rows = function () {
                    return Array.prototype.slice.call(
                        document.querySelectorAll(".ts-play[data-src]"));
                };

                document.addEventListener("keydown", function (event) {
                    // הקלדה בשדה חיפוש היא לא קיצור מקלדת
                    const tag = (event.target.tagName || "").toLowerCase();
                    if (tag === "input" || tag === "textarea"
                        || event.target.isContentEditable
                        || event.metaKey || event.ctrlKey || event.altKey) return;

                    const all = rows();
                    if (!all.length) return;
                    const active = current();
                    const at = active ? all.indexOf(active) : -1;

                    if (event.key === " " || event.code === "Space") {
                        event.preventDefault();
                        (active || all[0]).click();
                        return;
                    }
                    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                        event.preventDefault();
                        const step = event.key === "ArrowDown" ? 1 : -1;
                        const next = all[Math.min(Math.max(at + step, 0), all.length - 1)]
                            || all[0];
                        next.click();
                        next.scrollIntoView({block: "center", behavior: "smooth"});
                        return;
                    }
                    if (event.key === "l" || event.key === "L") {
                        const row = (active || all[0]).closest(
                            '[class*="st-key-trow_"]');
                        // הכפתור הראשון במכולת הפעולות של השורה הוא
                        // הלב (ראו `render_track`); בורר גנרי היה תופס
                        // את כפתור הנגינה שיושב לפניו בשורה
                        const love = row && row.querySelector(
                            '[class*="st-key-tacts_"] .stButton button');
                        if (love) { event.preventDefault(); love.click(); }
                    }
                }, true);

                // אירועי מדיה אינם עולים בבועה, ולכן האזנה בשלב ה-capture
                ["play", "pause", "ended"].forEach(function (name) {
                    document.addEventListener(name, function (event) {
                        if (event.target instanceof HTMLMediaElement) paint();
                    }, true);
                });

                // תצוגה מקדימה שכתובתה כבר לא חיה: לסמן, ולא להשאיר כפתור
                // שנראה תקין ולא עושה דבר
                document.addEventListener("error", function (event) {
                    const audio = media();
                    if (!audio || event.target !== audio) return;
                    document.querySelectorAll(".ts-play").forEach(function (button) {
                        if (button.dataset.id !== audio.dataset.playing) return;
                        button.classList.add("is-dead");
                        // ובלי זה הוא נשאר עם אייקון "עוצר" על שמע שלא רץ:
                        // ב-Safari `paused` לא בהכרח חוזר ל-true אחרי שגיאת
                        // טעינה, ולכן `paint` לבדה לא ניקתה את הסימון
                        button.classList.remove("is-playing");
                        button.title = "This version's preview is no longer available";
                    });
                }, true);

                // כפתורים שנוצרו ב-rerun מקבלים את המצב הנוכחי. מקובץ
                // ל-frame אחד ולא מורץ על כל מוטציה: במהלך חיפוש Streamlit
                // משנה את העץ ברצף, וסריקה של כל `.ts-play` בכל שינוי היא
                // עבודה מיותרת בדיוק ברגע שבו הדף גם נגלל.
                let queued = false;
                new MutationObserver(function () {
                    if (queued) return;
                    queued = true;
                    requestAnimationFrame(function () { queued = false; paint(); });
                }).observe(document.body, { childList: true, subtree: true });
            };

            const script = doc.createElement("script");
            script.textContent = "(" + code.toString() + ")();";
            doc.head.appendChild(script);
        })();
        </script>
        """,
        # st.iframe דורש גובה חיובי, בניגוד ל-components.html שקיבל 0
        height=1,
    )


def _keep_scroll_position():
    """מחזיר את מקום הגלילה כשהעמוד נבנה מחדש, כדי שלא יקפוץ לראש.

    כל לחיצה ב-Streamlit היא rerun, ולחיצת ❤️ מוסיפה עוד אחד מפורש (בלעדיו
    הלב לא מתחלף עד הפעולה הבאה). בדפדפנים שבהם עוגן הגלילה לא מחזיק, הבנייה
    מחדש של ה-DOM מקפיצה לראש והמשתמש מאבד את מקומו באמצע רשימה ארוכה.

    השומר חייב להיות MutationObserver מתמשך ולא סקריפט שרץ בטעינה: נמדד
    שה-iframe אינו מורכב מחדש ב-rerun (ה-srcdoc זהה), ולכן גרסה שרצה פעם
    אחת בכניסה פשוט לא נורתה כשהיה בה צורך.

    הוא פסיבי בכוונה — משחזר רק את הצירוף "היינו עמוק בעמוד, ואחרי בנייה
    מחדש אנחנו בראשו". גלילה שהמשתמש עשה בעצמו מעדכנת את הזיכרון ולכן אינה
    נגררת אחורה, וחיפוש חדש מאפס אותו דרך סמן הדור שב-DOM.
    """
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__scrollKeeperBound) return;
            doc.__scrollKeeperBound = true;

            const target = () => {
                const main = doc.querySelector('[data-testid="stMain"]');
                return (main && main.scrollHeight > main.clientHeight)
                    ? main : doc.scrollingElement;
            };

            let saved = 0, lastBuild = 0, generation = null, pending = null;

            doc.addEventListener("scroll", function () {
                if (pending) return;
                pending = setTimeout(function () {
                    pending = null;
                    const el = target();
                    if (!el) return;
                    // אפס שמגיע מיד אחרי בנייה מחדש הוא הקפיצה עצמה, לא
                    // גלילה של המשתמש — ולכן אינו נכנס לזיכרון
                    if (el.scrollTop >= 40 || Date.now() - lastBuild > 600) {
                        saved = Math.round(el.scrollTop);
                    }
                }, 120);
            }, true);

            new MutationObserver(function () {
                lastBuild = Date.now();
                const marker = doc.querySelector("[data-result-generation]");
                const now = marker ? marker.getAttribute("data-result-generation") : null;
                if (now !== generation) {
                    // רשימה חדשה: אין לאן לחזור, ומקום ברשימה הקודמת חסר משמעות
                    generation = now;
                    saved = 0;
                    return;
                }
                const el = target();
                if (el && saved > 200 && el.scrollTop < 40) {
                    requestAnimationFrame(function () {
                        const back = target();
                        if (back) back.scrollTop = saved;
                    });
                }
            }).observe(doc.body, {childList: true, subtree: true});
        })();
        </script>
        """,
        height=1,
    )


def youtube_music_url(artist: str, track: str) -> str:
    """קישור חיפוש ב-YouTube Music לגרסה הזו.

    חיפוש ולא מזהה טראק: אין לנו מזהה YouTube לגרסאות שמגיעות מ-iTunes או
    מ-Deezer, ולשלוף אותו היה דורש קריאת API לכל שורה. שאילתת "אמן שיר"
    נוחתת על הגרסה הנכונה, ועובדת בלי מפתח ובלי בקשה מהשרת.
    """
    return "https://music.youtube.com/search?q=" + quote_plus(f"{artist} {track}".strip())


def audio_player(url: str, ident: str = "", track: dict | None = None):
    """כפתור נגינה אחד. ההתנהגות והאודיו עצמו מגיעים מ-`_audio_behaviour`.

    `st.audio` מרנדר `<audio controls>`, ופקדי הדפדפן יושבים ב-shadow DOM
    שלא ניתן לעצב — ולכן הוא נראה כמו הדפדפן ולא כמו האפליקציה. כאן יש רק
    כפתור, והכתובת נוסעת עליו ב-`data-src` אל אלמנט האודיו המשותף.

    `ident` הוא זהות הגרסה (uid, או מפתח הפלייליסט): לפיו נקבע איזה כפתור
    מסומן כמנגן. לפי הכתובת לבדה שתי שורות של אותה גרסה היו נדלקות יחד.

    `track` נוסע על הכפתור כ-`data-artist`/`data-track`/`data-art` כדי
    שסרגל הנגן התחתון יוכל להתמלא **מתוך הדפדפן**, בלי סיבוב לפייתון ובלי
    rerun. זה מה שמאפשר לסרגל הזה להתקיים בכלל בתוך Streamlit: כל לחיצה
    כאן היא ריצה מחדש של הסקריפט, וסרגל שהיה נבנה בפייתון היה מהבהב בכל
    לחיצה על כל כפתור אחר בדף.

    בלי פס התקדמות ובלי שעון: התצוגה המקדימה היא שלושים שניות, אין לאן
    לדלג בתוכה, ובשורה הצרה הפס והשעון היו רוב הרוחב. השיר המלא נמצא
    מאחורי הקישור בשם השיר.
    """
    def attr(value: str) -> str:
        return html.escape(str(value or ""), quote=True)

    meta = ""
    if track:
        meta = (f" data-artist='{attr(track.get('artist'))}'"
                f" data-track='{attr(track.get('track'))}'"
                f" data-art='{attr(track.get('artwork'))}'"
                f" data-url='{attr(youtube_music_url(track.get('artist', ''), track.get('track', '')))}'")
    st.html(
        "<div class='ts-player'>"
        f"<button class='ts-play' type='button' data-src='{attr(url)}'"
        f" data-id='{attr(ident or url)}'{meta}"
        " aria-label='Play preview'></button>"
        "</div>")


# ---------- מצב ----------

# מי מבצע את הפעולה, פעם אחת לריצה. **לא** משתנה מודול שנקבע פעם אחת
# בטעינה: Streamlit מריץ כל session בת'רד משלו על אותו תהליך, ו-`SUBJECT`
# מחושב מחדש בכל ריצת סקריפט מתוך הקשר ה-session שלה. כל קריאה לאחסון
# אישי מקבלת אותו במפורש.
SUBJECT = accounts.current_subject()

# חסימת השמירה מותנית בכך שהתחברות בכלל מוגדרת. בפיתוח מקומי ובטסטים אין
# `[auth]`, ואז אין למי להתחבר — ולכן שם הכל נשאר כפי שהיה: משתמש יחיד
# שיכול לשמור. בפרודקשן, שבה auth מוגדרת, השמירה היא החומה.
LOGIN_ENABLED = accounts.login_available()


# ההתחברות אינה מתנה של מכסה חדשה: המכסה שנוצלה אנונימית עוברת לחשבון
# פעם אחת, ברגע המעבר. בלי זה "התחבר" היה הדרך המהירה ביותר לאפס מכסה.
if LOGIN_ENABLED and SUBJECT.is_logged_in and not st.session_state.get("_quota_merged"):
    st.session_state["_quota_merged"] = True
    accounts.merge_anonymous_quota(SUBJECT)


def _may_save() -> bool:
    if not LOGIN_ENABLED or SUBJECT.is_logged_in:
        return True
    st.toast("Log in to keep covers in your playlist.", icon=":material/lock:")
    return False


def _init_state():
    defaults = {
        "blacklist": storage.load_blacklist(SUBJECT),
        "favorites": storage.load_favorites(SUBJECT),
        "rejections": storage.load_rejections(SUBJECT),
        "candidates": [],
        "seen_keys": set(),
        "visible_count": PAGE_SIZE,
        # סדר התצוגה קפוא (ראו `ordered_display`): רשימת uid, החתימה שיצרה
        # אותה, ומונה שעולה בכל חיפוש חדש
        "display_order": [],
        "order_signature": None,
        "result_generation": 0,
        # מונה שמפתח האקספנדר של אינדקס המצעדים נגזר ממנו. העלאתו מרנדרת
        # רכיב חדש, שנולד מכווץ — ראו את ההסבר ליד האקספנדר עצמו
        "index_generation": 0,
        "recent_rolls": [],
        "last_query": "",
        "covers_source": "",
        "work_candidates": [],
        # השאילתה שעבורה נפתרו המועמדים. בלעדיה הבורר שרד שינוי של שם השיר,
        # ו-`work_id` של יצירה אחרת נשלח לחיפוש הבא
        "work_query": "",
        "bigness": {},
        "evidence": {},
        "original": None,
        "all_inputs": [],
        "artist_preview_query": "",
        "artist_preview_titles": [],
        "cors_retried": set(),
        "similar_of": None,
        "pending_fields": None,
        "index_source": SOURCE_CLASSICS,
        "search_mode": MODE_SONG,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def is_blacklisted(artist: str) -> bool:
    return clean_artist_name(artist).lower() in st.session_state["blacklist"]


def apply_blacklist(tracks: list[dict]) -> list[dict]:
    return [t for t in tracks if not is_blacklisted(t.get("artist", ""))]


def drop_seen(tracks: list[dict], seen) -> list[dict]:
    """מסיר את מה שכבר הוצג בסבב הזה, כש"רק מה שלא ראיתי" מסומן.

    ב-MODE_FREE הסינון קורה בתוך `search_covers` דרך `exclude_keys`, אבל שני
    המסלולים האחרים — קאברים לשיר ולאמן — לא קיבלו אותו כלל, והצ'קבוקס פשוט
    לא עשה דבר במצב שבו המשתמש נמצא רוב הזמן (נבדק).
    """
    if not seen:
        return tracks
    return [t for t in tracks
            if track_key(t.get("artist", ""), t.get("track", "")) not in seen]


# ---------- ❤️ פלייליסט וטעם נלמד ----------

# שדות שנשמרים בפלייליסט: מספיק כדי להציג את הגרסה מאוחר יותר, ומספיק כדי
# ללמוד ממנה. שמירת הטראק המלא הייתה גוררת גם שדות רגעיים כמו `score`.
# `uid` נשמר כדי שאפשר יהיה לפנות שוב למקור על גרסה שמורה — כתובת תצוגה
# מקדימה היא כתובת CDN ואין ערובה שתחיה לנצח
FAVORITE_FIELDS = ("artist", "track", "album", "genre", "year", "duration_sec",
                   "preview_url", "artwork", "source", "catalog_source",
                   "trailer_indicator", "uid")


def is_favorite(track: dict) -> bool:
    return track_key(track.get("artist", ""), track.get("track", "")) in st.session_state["favorites"]


def is_rejected(track: dict) -> bool:
    return track_key(track.get("artist", ""), track.get("track", "")) in st.session_state["rejections"]


def origin_of(track: dict) -> dict:
    """השיר המקורי שהגרסה הזו מכסה — המפתח שלפיו הפלייליסט מקובץ.

    `origin_track` מסומן ב-`covers.py` בחיפוש לפי אמן וב"עוד קאברים", אבל
    לא בחיפוש רגיל לפי שיר; שם הכותרת עצמה נושאת את התשובה אחרי ניקוי
    תגיות הגרסה (`clean_track_title` הקיימת: "Yellow (Epic Trailer
    Version)" ← "Yellow"). האמן המקורי הוא מה שהמשתמש הקליד בשדה האמן,
    או שאת הקטלוג שלו סרקנו — ולכן `cover_artist`.
    """
    # מה שהמשתמש חיפש קודם לניקוי הכותרת: שתי גרסאות של אותו שיר יכולות
    # להיקרא "Bitter Sweet Symphony" ו-"Bittersweet Symphony", והניקוי לבדו
    # היה מפצל אותן לשתי קבוצות. השאילתה זהה לשתיהן, ולכן היא המפתח הנכון.
    title = (track.get("origin_track")
             or (st.session_state.get("cover_title") or "").strip()
             or search_module.clean_track_title(track.get("track", ""))
             or track.get("track", ""))
    return {"track": title.strip(),
            "artist": (st.session_state.get("cover_artist") or "").strip()}


def origin_key(entry: dict) -> str:
    """מפתח הקיבוץ. לרשומות שנשמרו לפני שהשדה נוסף — נגזר בקריאה.

    זה מה שמייתר סקריפט מיגרציה: פלייליסט קיים מתקבץ נכון בלי לגעת
    ב-`favorites.json` של המשתמש.
    """
    origin = entry.get("origin") or {}
    title = (origin.get("track")
             or search_module.clean_track_title(entry.get("track", ""))
             or entry.get("track", ""))
    return track_key(origin.get("artist", ""), title)


def _snapshot(track: dict) -> dict:
    features = st.session_state["bigness"].get(track["uid"])
    return {
        **{field: track.get(field) for field in FAVORITE_FIELDS},
        # שיר המקור, כדי שהפלייליסט יוכל לשרשר את כל הגרסאות שלו יחד
        "origin": origin_of(track),
        # המדידה נשמרת ברגע התיוג כדי שהלמידה לא תהיה תלויה בכך שהטראק יימדד
        # שוב בעתיד; אם עוד לא נמדד, נלמד ממנו קטגוריאלית בלבד
        "features": features if audio.measured(features) else None,
        "added_at": time.time(),
        # מתי הכתובת נבדקה לאחרונה מול המקור. ראו `_stale_previews`.
        "preview_checked_at": time.time(),
    }


# כתובת preview היא כתובת CDN, והאפליקציה שמרה אותה ברגע הלייק והאמינה לה
# לנצח. אצל Deezer היא חתומה וקצרת-מועד, ואצל iTunes ארוכת-מועד אבל לא
# נצחית — וזה בדיוק מה שנראה בצילום: באותה קבוצה, שנשמרה באותו זמן, חלק
# מנגן וחלק לא. ההבדל הוא המקור, לא הגיל.
PREVIEW_TTL_SHORT = 6 * 3600      # Deezer
PREVIEW_TTL_LONG = 30 * 86400     # iTunes וכל השאר
AUTO_REFRESH_CAP = 40             # תקרה למעבר אחד; השאר במעבר הבא


def _stale_previews(favorites: dict, now: float | None = None,
                    cap: int = AUTO_REFRESH_CAP) -> list[str]:
    """המפתחות שכתובת התצוגה המקדימה שלהם כנראה כבר לא חיה.

    טהורה בכוונה — בחירת המועמדים היא ההיגיון שאפשר לבדוק בלי רשת, ולכן
    היא מופרדת מהבקשות עצמן. רשומה בלי כתובת כלל אינה מועמדת: אין לה מה
    להתיישן, והיא מוצגת ממילא עם מציין "אין תצוגה מקדימה".
    """
    now = now or time.time()
    stale = []
    for key, entry in favorites.items():
        if not entry.get("preview_url"):
            continue
        ttl = (PREVIEW_TTL_SHORT if (entry.get("source") or "").lower() == "deezer"
               else PREVIEW_TTL_LONG)
        checked = entry.get("preview_checked_at")
        try:
            checked = float(checked)
        except (TypeError, ValueError):
            checked = 0.0          # מעולם לא נבדקה
        if now - checked >= ttl:
            stale.append(key)
    return stale[:cap]


# המפתח שבו נשמרת תוצאת הריענון האחרון. `refresh_previews` מסתיימת
# ב-`st.rerun()`, ולכן ערך חזרה רגיל לא היה מגיע לקורא לעולם — התוצאה
# חייבת לשרוד את הריצה מחדש.
REFRESH_NOTE = "preview_refresh_note"


def refresh_previews(favorites: dict, keys: list[str] | None = None,
                     quiet: bool = False):
    """מבקש כתובת תצוגה מקדימה חיה, ושומר.

    `keys` — תת-קבוצה לרענון (ברירת מחדל: הכל). `quiet` — ספינר קצר במקום
    פס התקדמות, למעבר האוטומטי שרץ בלי שביקשו אותו.

    הבקשות במקביל מאותה סיבה שהחיפוש מקבילי: שבעים גרסאות בזו אחר זו הן
    דקות של המתנה.
    """
    entries = [(key, favorites[key]) for key in (keys or list(favorites))
               if key in favorites]
    if not entries:
        return
    now = time.time()
    changed, missing = 0, 0
    progress = None if quiet else st.progress(0.0, text="Requesting fresh links...")
    spinner = st.spinner(f"Refreshing playback links ({len(entries)})...") if quiet else None
    if spinner:
        spinner.__enter__()
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            def resolve(item):
                key, entry = item
                try:
                    return (key, *search_module.refresh_preview(entry, client=client))
                except Exception:
                    # גרסה אחת שנכשלה לא מפילה את הריענון כולו
                    return key, "", ""

            with ThreadPoolExecutor(max_workers=8) as pool:
                for index, (key, url, uid) in enumerate(pool.map(resolve, entries)):
                    if progress:
                        progress.progress((index + 1) / len(entries),
                                          text=f"{index + 1}/{len(entries)}")
                    # נבדקה — גם כשלא נמצאה כתובת. אחרת אותה רשומה תיבדק
                    # שוב בכל rerun והמעבר האוטומטי לא ייגמר לעולם.
                    favorites[key]["preview_checked_at"] = now
                    if not url:
                        # כתובת ישנה שאולי עובדת עדיפה על שדה ריק: כך תקלת
                        # רשת חד-פעמית לא מרוקנת את הפלייליסט
                        missing += 1
                        continue
                    # ה-uid נשמר גם כשהכתובת לא השתנתה: הריענון הבא יהיה אז
                    # שאילתה ישירה במקום חיפוש בחנות
                    if uid and not favorites[key].get("uid"):
                        favorites[key]["uid"] = uid
                    if url != favorites[key].get("preview_url"):
                        favorites[key]["preview_url"] = url
                        changed += 1
    finally:
        if spinner:
            spinner.__exit__(None, None, None)
    if progress:
        progress.empty()
    storage.save_favorites(favorites, SUBJECT)
    # כישלון שקט הוא מה שהחזיר את הבאג הזה שוב ושוב: המשתמש ראה ספינר,
    # אחריו כפתורים אפורים, ובלי מילה אחת של הסבר. הספירה נשמרת כדי
    # שהסרגל יוכל לומר מה קרה — גם במעבר האוטומטי, שהוא בדיוק המקרה
    # שבו איש לא ביקש את הריענון ולכן איש לא מצפה לתוצאה שלו.
    st.session_state[REFRESH_NOTE] = {
        "changed": changed, "missing": missing, "total": len(entries),
    }
    st.rerun()


def toggle_favorite(track: dict):
    """מוסיף או מסיר מהפלייליסט. הפלייליסט הוא גם מאגר האימון החיובי."""
    if not _may_save():
        return
    favorites, rejections = st.session_state["favorites"], st.session_state["rejections"]
    key = track_key(track.get("artist", ""), track.get("track", ""))
    if key in favorites:
        favorites.pop(key)
    else:
        favorites[key] = _snapshot(track)
        # אותו טראק לא יכול להיות גם אהוב וגם דחוי
        if rejections.pop(key, None) is not None:
            storage.save_rejections(rejections, SUBJECT)
    storage.save_favorites(favorites, SUBJECT)


def toggle_rejection(track: dict):
    """מסמן "לא זה". דוגמאות שליליות הן שנותנות ללמידה כיוון ולא רק מרכז."""
    if not _may_save():
        return
    favorites, rejections = st.session_state["favorites"], st.session_state["rejections"]
    key = track_key(track.get("artist", ""), track.get("track", ""))
    if key in rejections:
        rejections.pop(key)
    else:
        rejections[key] = _snapshot(track)
        if favorites.pop(key, None) is not None:
            storage.save_favorites(favorites, SUBJECT)
    storage.save_rejections(rejections, SUBJECT)


def taste_profile(background: list[dict] | None = None) -> dict:
    """הפרופיל הנלמד. הרקע הוא פול התוצאות המוצג, ובלעדיו זה מונה שכיחות."""
    return taste.profile(list(st.session_state["favorites"].values()), background,
                         rejections=list(st.session_state["rejections"].values()))


def taste_of(track: dict, learned: dict) -> float:
    return taste.match(track, st.session_state["bigness"].get(track["uid"]), learned)


def queue_fields(title: str = "", artist: str = "", mode: str | None = None,
                 auto_run: bool = False):
    """קובע את שדות החיפוש (ואופציונלית מצב + הרצה אוטומטית) מכפתור, ומרענן.

    Streamlit אוסר על שינוי session_state של widget אחרי שהוא נוצר, ולכן אי אפשר
    לכתוב לשדה מתוך כפתור שמצויר מתחתיו. הערך נשמר כאן ומוחל בתחילת הריצה הבאה,
    לפני שהשדות/הרדיו נוצרים.
    """
    st.session_state["pending_fields"] = (title, artist, mode, auto_run)
    st.rerun()


def _render_saved_versions(versions: list, favorites: dict):
    """הגרסאות של שיר מקור אחד: כפתור נגינה, שם האמן, והסרה.

    שם השיר לא חוזר בכל שורה — הוא כותרת הקבוצה, וכל השורות מתחתיו הן
    אותו שיר. מה שמבדיל בין השורות הוא האמן, ולכן הוא הטקסט היחיד.
    """
    for key, entry in versions:
        row = st.container(key=f"favrow_{key}", horizontal=True,
                           wrap=False, vertical_alignment="center")
        with row:
            # ישירות בשורה ולא בתוך popover: קודם היו דרושות שתי הקשות
            # כדי להתחיל לנגן, ואחת מהן פתחה חלון שכל תוכנו כפתור נגינה
            if entry.get("preview_url"):
                audio_player(entry["preview_url"], ident=f"fav-{key}")
            else:
                st.html("<div class='ts-player ts-noplay'"
                        " title='No preview available'></div>")
            # לחיצה על שם האמן מחזירה לגרסה: ממלאת את השדות ומריצה חיפוש
            # לשיר הזה, כדי שאפשר יהיה למצוא אותה ואת מה שדומה לה שוב
            if st.button(entry.get("artist", "") or entry.get("track", ""),
                         key=f"fav_open_{key}", type="tertiary", width="stretch",
                         help=f"{entry.get('artist', '')} — {entry.get('track', '')}"):
                # חזרה ל-Discover, אחרת החיפוש רץ מאחורי מסך הפלייליסט
                # ואף אחד לא רואה אותו — `queue_fields` קובע את השדות,
                # אבל השדות עצמם לא נוצרים כלל במסך הזה
                st.session_state["rail_nav"] = NAV_DISCOVER
                queue_fields(entry.get("track", ""), entry.get("artist", ""),
                             mode=MODE_SONG, auto_run=True)
            # העתקה מהירה של "אמן — שיר": זה מה שמודבק לתוכנת העריכה,
            # לחוזה רישוי או לחיפוש. `st.html` ולא `st.button`, כי לחיצה
            # שמעתיקה לא צריכה סיבוב לפייתון — היא נגמרת בדפדפן, באותו
            # frame, בלי rerun שיעצור את מה שמתנגן. הטיפול עצמו יושב
            # ב-`_audio_behaviour`, באותה האזנה מוסמכת כמו כפתורי הנגינה.
            _copy = " — ".join(part for part in (entry.get("artist", ""),
                                                 entry.get("track", "")) if part)
            if _copy:
                _safe = html.escape(_copy, quote=True)
                st.html(f"<button class='ts-copy' type='button' data-copy='{_safe}'"
                        f" title='Copy &quot;{_safe}&quot;'"
                        " aria-label='Copy artist and title'></button>")
            if st.button("", key=f"unfav_{key}", icon=":material/close:",
                         type="tertiary", help="Remove from Loved"):
                favorites.pop(key)
                storage.save_favorites(favorites, SUBJECT)
                st.rerun()


# ---------- סרגל הצד: ה-rail ----------

# ארבעה פריטי ניווט, ולא כל התוכן זה מתחת לזה. קודם הסרגל החזיק את
# הפלייליסט, את ההגדרות, את הרשימה השחורה ואת הדחיות ברצף אחד — מה
# שהפך אותו לעמוד שני שגוללים בו, ולא לניווט. כאן הוא בוחר **מה מוצג**,
# וזה גם מה שמאפשר לאינדקס המצעדים לרדת מהאקספנדר שבאמצע המסך.
NAV_DISCOVER, NAV_CHARTS, NAV_LOVED, NAV_SETTINGS = (
    "Discover", "Charts", "Loved", "Settings")
NAV_ITEMS = (NAV_DISCOVER, NAV_CHARTS, NAV_LOVED, NAV_SETTINGS)

if "rail_nav" not in st.session_state:
    st.session_state["rail_nav"] = NAV_DISCOVER


def _rail_nav():
    """פריטי הניווט.

    הפעיל מסומן דרך **מפתח** שונה (`nav_<item>_on`) ולא דרך מחלקה: אין
    ל-Streamlit דרך לתת class למכולה, אבל ה-key מפיק `st-key-<key>` על
    האלמנט — ולכן זו הדרך הנתמכת לתפוס "הפריט הפעיל" ב-CSS.
    """
    current = st.session_state["rail_nav"]
    for item in NAV_ITEMS:
        active = item == current
        row = st.container(key=f"nav_{item}{'_on' if active else ''}",
                           horizontal=True, vertical_alignment="center")
        with row:
            if st.button(item, key=f"navbtn_{item}", type="tertiary",
                         width="stretch"):
                st.session_state["rail_nav"] = item
                st.rerun()
            # המונה על Loved הוא המספר היחיד ב-rail, ולכן הוא ב-mono
            # ובענבר: זה הדבר היחיד כאן שמשתנה תוך כדי עבודה
            if item == NAV_LOVED and st.session_state["favorites"]:
                st.html("<span class='ts-navcount'>"
                        f"{len(st.session_state['favorites'])}</span>")


def _rail_account():
    """התחברות והמכסה שנשארה. מוצג רק כשהתחברות בכלל מוגדרת."""
    if not LOGIN_ENABLED:
        return
    st.html("<div class='ts-railrule'></div>")
    if SUBJECT.is_logged_in:
        st.html("<div class='ts-railcap'>SIGNED IN</div>"
                f"<p class='ts-railtaste'>{html.escape(SUBJECT.email or '')}</p>")
        if st.button("Log out", key="btn_logout", type="tertiary", width="stretch"):
            st.logout()
    else:
        st.html("<div class='ts-railcap'>GUEST</div>"
                "<p class='ts-railtaste'>Log in to keep a playlist. Without an "
                "account you can search and listen, but nothing is saved.</p>")
        if st.button("Log in with Google", key="btn_login", type="tertiary",
                     width="stretch"):
            st.login()
    left = int(accounts.remaining(SUBJECT))
    st.html("<div class='ts-railcap'>SEARCHES LEFT "
            f"<span class='ts-navcount'>{left}</span></div>")


def _remember_anon():
    """כותב את הזהות האנונימית לעוגייה, כדי שהמכסה תשרוד רענון.

    **אמירה כנה: זה מהמור, לא חומה.** ניקוי עוגיות או חלון פרטי מייצרים
    זהות חדשה ומכסה חדשה. לא משתמשים ב-IP במקום: התיעוד של Streamlit
    אומר במפורש שאסור להשתמש בו לאבטחה כי קל לזייף אותו. החומה האמיתית
    כאן היא השמירה, שדורשת התחברות.

    הכתיבה היא ל-`window.parent.document` ולא לתוך ה-iframe, מאותה סיבה
    שמתוארת ב-`_audio_behaviour`: ל-iframe יש origin משלו, ועוגייה
    שתיכתב בו לא תגיע לעולם לשרת.
    """
    if not LOGIN_ENABLED or SUBJECT.is_logged_in:
        return
    value = SUBJECT.key.split(":", 1)[-1]
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        f"""
        <script>
        (function () {{
            const doc = window.parent.document;
            const name = {accounts.ANON_COOKIE!r};
            const has = doc.cookie.split('; ').some(c => c.indexOf(name + '=') === 0);
            if (!has) {{
                doc.cookie = name + '={value}; path=/; max-age=31536000; SameSite=Lax';
            }}
        }})();
        </script>
        """, height=1)


def _rail_taste():
    """בלוק YOUR TASTE: מה הדירוג למד, במשפט אחד ובאותיות רגילות."""
    st.html("<div class='ts-railcap'>YOUR TASTE</div>")
    # שלוש תכונות ולא חמש: ברוחב 210px חמש נשברות לשש שורות ודוחפות את
    # RECENT מתחת לקפל. התמונה המלאה נשארת זמינה ב-⋯ של כל שורה.
    summary = taste.describe(taste_profile(), limit=3)
    st.html(f"<p class='ts-railtaste'>{html.escape(summary)}</p>" if summary
            else "<p class='ts-railtaste'>Nothing learned yet. Love a few "
                 "covers and the ranking starts leaning your way.</p>")


def _rail_recent():
    """RECENT בתחתית ה-rail — מה שהוגרל לאחרונה, מהחדש לישן."""
    recent = list(reversed(st.session_state["recent_rolls"]))
    if not recent:
        return
    st.html("<div class='ts-railcap'>RECENT</div>")
    for artist, track in recent[:4]:
        st.html("<div class='ts-railrecent'>"
                f"{html.escape(track)} · {html.escape(artist)}</div>")


# מפתחות ה-widget שחייבים לשרוד מעבר בין מסכים. Streamlit מוחק
# מ-`session_state` מפתח של widget שלא נוצר בריצה מסוימת, ומסכי Loved
# ו-Settings עוצרים את הסקריפט לפני שדות החיפוש — כלומר בלי המראה
# הזאת, ביקור בפלייליסט היה מוחק את השאילתה שהמשתמש הקליד.
# זה בדיוק אותו כשל שכבר תפס את שדה האמן כשהוחלף ב-chip.
SCREEN_SAFE_KEYS = (
    "cover_title", "cover_artist", "search_mode", "sort_by",
    "bucket_filter", "filter_style", "filter_length", "filter_recency",
    "filter_prefer_new", "filter_fresh_only", "filter_same_work",
    "filter_sound",
)


def _remember_screen_state():
    """מעתיק את מצב הפקדים לעותק שאינו widget, לפני שהסקריפט נעצר."""
    for key in SCREEN_SAFE_KEYS:
        if key in st.session_state:
            st.session_state[f"kept_{key}"] = st.session_state[key]


def _restore_screen_state():
    """מחזיר את המצב לפני שהפקדים נוצרים מחדש."""
    for key in SCREEN_SAFE_KEYS:
        if key not in st.session_state and f"kept_{key}" in st.session_state:
            st.session_state[key] = st.session_state[f"kept_{key}"]


def _loved_screen():
    """הפלייליסט, בעמודה הראשית: קבוצות לפי שיר המקור, ריענון, וייצוא.

    **לא ב-rail.** הגרסה הראשונה רינדרה אותו בתוך סרגל של 210px, ומאה
    וארבעים גרסאות מקובצות לפי שיר הפכו שם לעמודת כרטיסים שכל כותרת בה
    נשברה לשלוש שורות. ה-rail הוא ניווט; זה מסך תוכן, והוא צריך את
    הרוחב של העמודה הראשית — בדיוק כמו התוצאות.
    """
    favorites = st.session_state["favorites"]

    # מקובץ לפי שיר המקור, ולא רשימה שטוחה: כל הגרסאות של אותו שיר
    # יושבות יחד, וזו גם הדרך שבה חושבים על פלייליסט של קאברים.
    groups: dict[str, list[tuple[str, dict]]] = {}
    for key, entry in favorites.items():
        groups.setdefault(origin_key(entry), []).append((key, entry))

    st.html(
        "<div class='ts-resulthead'>"
        f"<h2 class='ts-h2'>{len(favorites)} loved cover"
        f"{'' if len(favorites) == 1 else 's'}</h2>"
        + (f"<span class='ts-lede'>across {len(groups)} song"
           f"{'' if len(groups) == 1 else 's'} · newest first</span>"
           if groups else "")
        + "</div>")

    if not favorites:
        st.caption("Tap the heart next to a cover you like. It is saved here, "
                   "and the ranking learns what your taste looks like.")
        return

    # הריענון קורה מעצמו. כל פתרון שדורש מהמשתמש להבחין בכפתור אפור
    # וללחוץ על משהו הוא טלאי: הכתובות מתות בין סשנים, והמשתמש מגלה
    # זאת רק כשהוא לוחץ נגן ולא שומע כלום.
    _stale = _stale_previews(favorites)
    if _stale:
        refresh_previews(favorites, keys=_stale, quiet=True)

    # שתי פעולות המסך בשורה אחת בראשו, ולא אחת למעלה ואחת מתחת לכל
    # הקבוצות: עם מאה וארבעים גרסאות מכווצות, כפתור שיושב מתחתיהן פשוט
    # לא נמצא.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["origin song", "origin artist", "artist", "track", "album",
                     "genre", "year", "preview"])
    # ממוין באותו קיבוץ כמו במסך, אחרת הקובץ מאבד את מה שהמסך מראה
    for _, entry in sorted(favorites.items(), key=lambda item: (
            origin_key(item[1]), -item[1].get("added_at", 0))):
        origin = entry.get("origin") or {}
        writer.writerow([origin.get("track", ""), origin.get("artist", ""),
                         entry.get("artist", ""), entry.get("track", ""),
                         entry.get("album", ""), entry.get("genre", ""),
                         entry.get("year", ""), entry.get("preview_url", "")])

    with st.container(key="lovedactions", horizontal=True,
                      vertical_alignment="center"):
        # הכפתור הוא מוצא אחרון ומתעלם מה-TTL — לגרסה שמתה באמצע סשן
        if st.button("Refresh playback links", icon=":material/refresh:",
                     help="A preview URL is a CDN URL and does not live forever. "
                          "A greyed-out play button is a version whose URL has "
                          "died — this asks the store for a fresh one."):
            refresh_previews(favorites)   # הכל, בלי קשר ל-TTL
        st.download_button("Export playlist", icon=":material/download:",
                           data=buffer.getvalue().encode("utf-8-sig"),
                           file_name="playlist.csv", mime="text/csv")

    _note = st.session_state.pop(REFRESH_NOTE, None)
    if _note and _note["missing"]:
        if _note["missing"] == _note["total"]:
            # כולן נכשלו. גרסאות שנמחקו מהחנות אינן נכשלות יחד, ולכן
            # זו כמעט תמיד תקלת רשת או שינוי בצד החנות
            st.warning(f"Could not get a fresh playback link for any of the "
                       f"{_note['total']} versions checked. Most likely a "
                       f"network problem — the old links were kept, try again "
                       f"in a moment.")
        else:
            st.caption(f"{_note['missing']} of {_note['total']} had no live "
                       f"link — their play button stays greyed out.")

    def newest(items) -> float:
        return max(entry.get("added_at", 0) for _, entry in items)

    for versions in sorted(groups.values(), key=newest, reverse=True):
        versions.sort(key=lambda item: item[1].get("added_at", 0), reverse=True)
        origin = versions[0][1].get("origin") or {}
        song = (origin.get("track")
                or search_module.clean_track_title(versions[0][1].get("track", ""))
                or versions[0][1].get("track", ""))
        by = origin.get("artist")
        # בלי מונה גרסאות: הן ממילא נספרות במבט אחד ברגע שפותחים את
        # הקבוצה, והמילה בכל שורה הייתה טקסט שממלא מסך.
        label = song + (f" · {by}" if by else "")
        # מכווץ כברירת מחדל: מאה וארבעים גרסאות פרושות הן מסך שאי
        # אפשר לגלול בו אל שום דבר
        with st.container(key=f"lovedgroup_{origin_key(versions[0][1])}"):
            with st.expander(label, expanded=False):
                _render_saved_versions(versions, favorites)


def _legacy_playlist_size() -> int:
    """כמה גרסאות תקועות במרחב המשותף מלפני ההתחברות.

    `subject=None` ולא `SUBJECT`: זו בדיוק הכניסה למרחב המשותף לפי
    ההגדרה של ה-facade (`storage._personal`), ולכן אין צורך לא בקריאת
    קובץ ידנית ולא בפונקציה פרטית — כולל טיפול בקובץ פגום, שכבר קיים שם.
    """
    if not LOGIN_ENABLED:
        return 0
    return len(storage.load_favorites(None))


def _settings_screen():
    """הגדרות, ייבוא מצעד, דחיות ורשימה שחורה — גם הוא מסך ולא סרגל."""
    st.html("<div class='ts-resulthead'><h2 class='ts-h2'>Settings</h2></div>")
    st.caption(f"Data folder: `{storage.DATA_DIR or 'unavailable'}`")
    _stranded = _legacy_playlist_size()
    if _stranded:
        # הפתעה שקטה היא הכשל שהקוד הזה כבר נכווה בו כמה פעמים. ברגע
        # שההתחברות נדלקת, פלייליסט שנצבר לפניה נשאר במרחב המשותף —
        # כלומר המשתמש המחובר רואה מסך ריק בזמן שכל מבקר אנונימי רואה
        # את האוסף. עדיף לומר את זה במפורש מאשר לתת לו לגלות לבד.
        st.warning(f"{_stranded} saved versions are still in the shared space "
                   "from before sign-in existed — you cannot see them while "
                   "logged in, but anonymous visitors can. Move them to your "
                   "account with:\n\n"
                   "`python tools/adopt_data.py --email you@example.com --commit`")
    if not youtube_module.available():
        # מידע על פיצ'ר כבוי, לא שלב במסלול — ולכן כאן ולא בין התוצאות
        st.caption("Trailer-usage verification is off (set YOUTUBE_API_KEY)")

    with st.expander("Import a Billboard chart", icon=":material/upload:"):
        st.caption("Save a chart page from your browser (Ctrl+S / Cmd+S) and "
                   "upload it here. billboard.com has no public API and blocks "
                   "servers, so the import goes through your browser, where "
                   "the page already loaded.")
        uploaded = st.file_uploader("Saved chart page:", type=["html", "htm"],
                                    key="chart_upload")
        if uploaded is not None and st.button("Import"):
            chart = billboard_module.parse_chart(
                uploaded.getvalue().decode("utf-8", errors="ignore"))
            if not chart["entries"]:
                st.error("No chart rows were recognised on that page.")
            else:
                slug = billboard_module.chart_slug(chart["title"])
                stored = storage.load_charts()
                stored[slug] = {**chart, "slug": slug}
                if storage.save_charts(stored):
                    st.success(f"Imported {len(chart['entries'])} rows from "
                               f"'{chart['title']}'")
                    st.rerun()
                else:
                    st.error("No writable data folder — the chart was not saved.")

        stored = storage.load_charts()
        if stored:
            to_remove = st.selectbox("Remove a chart:",
                                     [""] + [c["title"] for c in stored.values()])
            if to_remove and st.button("Remove"):
                storage.save_charts({slug: chart for slug, chart in stored.items()
                                     if chart["title"] != to_remove})
                st.rerun()

    # הדחיות אינן פלייליסט ולכן אינן מוצגות כרשימה — הן רק מלמדות
    if st.session_state["rejections"]:
        with st.expander(f"Marked 'not this' ({len(st.session_state['rejections'])})"):
            st.caption("Rejections are not hidden from the results — they only "
                       "teach the ranking to move away from that style. To hide "
                       "an artist completely, use Block artist.")
            if st.button("Clear rejections", icon=":material/delete:"):
                st.session_state["rejections"] = {}
                storage.save_rejections({}, SUBJECT)
                st.rerun()

    # החסימה עצמה נשארת פעילה; רק התצוגה שלה ירדה מהחזית לטובת הפלייליסט
    with st.expander(f"Blocked artists ({len(st.session_state['blacklist'])})"):
        blacklist = sorted(st.session_state["blacklist"])
        if not blacklist:
            st.caption("No blocked artists.")
        for artist in blacklist:
            row = st.container(key=f"unblock_row_{artist}", horizontal=True,
                               vertical_alignment="center")
            with row:
                st.write(artist)
                if st.button("", key=f"unblock_{artist}", type="tertiary",
                             icon=":material/undo:", help="Unblock"):
                    st.session_state["blacklist"].discard(artist)
                    storage.save_blacklist(st.session_state["blacklist"], SUBJECT)
                    st.rerun()

        if blacklist and st.button("Clear blocked artists",
                                   icon=":material/delete:"):
            st.session_state["blacklist"] = set()
            storage.save_blacklist(st.session_state["blacklist"], SUBJECT)
            st.rerun()


with st.sidebar:
    # ה-wordmark: ריבוע ענבר עם חור כהה — תקליט, לא ריבוע מלא
    st.html("<div class='ts-brand'><div class='ts-mark'></div>"
            "<span class='ts-word'>COVER<br>LOVER</span></div>")

    # ה-rail הוא **ניווט בלבד**, בכל המסכים. הפלייליסט וההגדרות ירדו
    # ממנו לעמודה הראשית: הם מסכי תוכן, ובסרגל של 210px מאה וארבעים
    # גרסאות מקובצות הפכו לעמודת כרטיסים שכל כותרת בה נשברה לשלוש שורות.
    _rail_nav()
    _rail_account()
    st.html("<div class='ts-railrule'></div>")
    _rail_taste()
    st.html("<div class='ts-railfill'></div>")
    _rail_recent()

    for warning in storage.warnings:
        st.warning(warning)

_remember_anon()


# ---------- מדידת גודל בדפדפן ----------

_MEASURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "components", "audio_meter")
_audio_meter = components.declare_component("audio_meter", path=_MEASURE_DIR)
# מופע שני לאותו רכיב: המסלול הישיר והמעקף רצים באותו rerun וצריכים key נפרד
_audio_meter_proxy = components.declare_component("audio_meter_proxy", path=_MEASURE_DIR)

# כמה טראקים לעקוף בכל סבב. ה-data URI הוא מגה-בייטים, וכולם עוברים דרך הדף
CORS_FALLBACK_BATCH = 4


def measure_visible(tracks: list):
    """מודד את כל המוצגים אוטומטית, בדפדפן של המשתמש.

    המדידה חייבת לרוץ בצד הלקוח: פענוח אודיו בשרת דורש תלות כבדה, והשרת הזה
    ממילא חסום לחלק מהחנויות. מה שכבר נמדד נשמר לקאש לפי track_key ולא נמדד שוב.
    """
    cache = storage.load_bigness()
    pending = []
    for track in tracks:
        uid = track["uid"]
        if uid in st.session_state["bigness"]:
            continue
        key = track_key(track["artist"], track["track"])
        if key in cache:
            st.session_state["bigness"][uid] = cache[key]
        elif track.get("preview_url"):
            pending.append({"uid": uid, "url": track["preview_url"]})

    if not pending:
        return

    results = _audio_meter(tracks=pending, key="audio_meter", default=None)
    if not results:
        st.caption("Measuring loudness in your browser\u2026")
        return

    _merge_results(results, tracks, cache, overwrite=False)


def _merge_results(results: dict, tracks: list, cache: dict, overwrite: bool):
    """מכניס מדידות ל-session_state ולקאש, ומרענן כדי שהשורות יתעדכנו."""
    by_uid = {t["uid"]: t for t in tracks}
    fresh, cacheable = False, False
    for uid, features in results.items():
        if not overwrite and uid in st.session_state["bigness"]:
            continue
        st.session_state["bigness"][uid] = features
        fresh = True
        track = by_uid.get(uid)
        # שגיאה לא נכנסת לקאש: היא עשויה להיות זמנית, ו"לא נמדד" אינו תוצאה
        if track and not features.get("error"):
            cache[track_key(track["artist"], track["track"])] = features
            cacheable = True
    if cacheable:
        storage.save_bigness(cache)
    if fresh:
        # גם כשהכל נכשל: השורות כבר רונדרו, בלי rerun ה-⚪ לא יופיע עד הקליק הבא
        st.rerun()


def measure_via_server(tracks: list):
    """מעקף לחסימת CORS: השרת מושך את הבייטים, הדפדפן עדיין מפענח ומודד.

    רץ רק על מה שנכשל במסלול הישיר, בקבוצות קטנות — כל preview עובר דרך הדף
    כ-data URI. כל טראק מנוסה פעם אחת בלבד, אחרת סבב שנכשל היה חוזר בלולאה.
    """
    blocked = [t for t in tracks
               if st.session_state["bigness"].get(t["uid"], {}).get("error") == "cors_failed"
               and t["uid"] not in st.session_state["cors_retried"]]
    if not blocked:
        return

    batch = blocked[:CORS_FALLBACK_BATCH]
    payload, failures = [], {}
    with st.spinner("Fetching the preview through the server (the store blocks direct measurement)\u2026"):
        for track in batch:
            data_uri, error = preview_module.fetch_data_uri(track.get("preview_url", ""))
            if error:
                failures[track["uid"]] = {"error": error}
            else:
                payload.append({"uid": track["uid"], "url": data_uri})

    cache = storage.load_bigness()
    if failures:
        st.session_state["cors_retried"].update(failures.keys())
        _merge_results(failures, tracks, cache, overwrite=True)
    if not payload:
        return

    results = _audio_meter_proxy(tracks=payload, key="audio_meter_proxy", default=None) or {}
    # הרכיב מחזיק את הערך של הסבב הקודם עד שה-JS שולח חדש. בלי הסינון הזה היינו
    # ממזגים שוב את אותן תוצאות בכל rerun, ועם overwrite זו לולאה אינסופית
    sent = {item["uid"] for item in payload}
    measured_now = {uid: features for uid, features in results.items() if uid in sent}
    if not measured_now:
        st.caption(f"Measuring {len(payload)} tracks through the server\u2026")
        return

    st.session_state["cors_retried"].update(measured_now.keys())
    _merge_results(measured_now, tracks, cache, overwrite=True)


# ---------- סדר התצוגה ----------

# משקלי הדירוג הראשי. שלושתם באותה סקאלה 0..1, ולכן הם מתחרים ולא
# מבטלים זה את זה — בניגוד למיון לקסיקוגרפי, שבו המפתח הראשון מכריע לבדו.
# המשקלים כוילו מול שלושה מקרים ולא לפי תחושה:
#   א. בלי שום למידה, גרסה שכתוב עליה "Epic Trailer Version" חייבת לעלות
#      מעל קאבר פופ רועש — גם כשהיא עצמה טרם נמדדה  (0.30 מול 0.10)
#   ב. אחרי שישה ❤️ על סגנון רגוע, גרסה רגועה חייבת לנצח גרסה "אפית"
#      רועשת עם שני סימני טריילר                     (0.41 מול 0.34)
#   ג. אחרי ארבעה 👎 על סגנון, טראק מאותו סגנון יורד (0.46 מול 0.29)
# משקל טעם של 0.40 נכשל ב-(ג), 0.55 נכשל ב-(ב), 0.65 עובר את שלושתם
# במרווח נוח. הפריור על טריילר הוא מה שקובע כשאין עדיין מה ללמוד ממנו:
# `taste_of` מחזיר 0 לכולם עד הלייק הראשון.
RANK_TASTE = 0.55      # מה שהמשתמש לימד בפועל — גובר על הפריור
RANK_WORK = 0.35       # הקטלוג מאשר שזו גרסה של השיר שביקשת
RANK_TRAILER = 0.18    # עדות מפורשת שזו גרסת טריילר — הסיבה שהאפליקציה קיימת
RANK_SIZE = 0.07       # המדידה בדפדפן. יש גם מיון מפורש "גודל (נמדד)"
# "טרם נמדד" אינו "קטן". הערך הקודם היה -1, ולכן כל טראק שהמדידה לא הגיעה
# אליו (אין preview, חסימת CORS, כישלון) צנח לתחתית — גם כשכתוב עליו
# במפורש "Epic Trailer Version" ויש לו שני סימני טריילר.
NEUTRAL_SIZE = 0.5


def rank_score(track: dict, learned: dict, measurements: dict) -> float:
    """הדירוג הראשי: טעם, אימות מול הקטלוג, עדות טריילר ומדידה.

    קודם המפתח היה `(taste, measured_size, score)` לקסיקוגרפית. בלי לייקים
    הטעם היה 0 לכולם, ולכן הגודל הנמדד הכריע לבדו ו-`score` — שכולל את
    `epic_bonus` — לא נגע בסדר בפועל. נמדד: טראק בשם "Zombie (Epic Trailer
    Version)", ז'אנר Soundtrack, ציון 130 מול 100, דורג **אחרון** מול קאבר
    פופ רגיל שנמדד רועש. זה ההפך ממה שהאפליקציה אמורה לעשות.

    `RANK_WORK` נוסף אחרי התלונה ההפוכה: גרסת טריילר טובה במקום 1, אחריה
    שמונה-עשרה קיו-ים גנריים מספריות הפקה, ובמקום 20 קאבר אמיתי ומצוין.
    נמדד בסימולציה שפרישת הטעם על פני הפול תורמת לציון 0.161 בסך הכל,
    בעוד שהכרזת טריילר בודדת תורמת 0.250 — כלומר סימן בינארי אחד שוקל
    יותר מכל טווח הטעם הנלמד. ספריות הפקה מכריזות על עצמן כטריילר
    בהגדרה, זה המוצר שלהן, וקאבר של להקה אמיתית לא; לכן רבע מהדירוג היה
    מוטה שיטתית לטובת החומר הגנרי.

    האות שמפריד ביניהם הוא `work_verified`: הקטלוג פותר את *היצירה*
    ומחזיר רק גרסאות שלה, וקיו בשם "Stayin' Alive Epic Trailer" אינו
    ביניהן. במסלולים שאינם "קאברים לשיר" אף תוצאה אינה נושאת את השדה,
    הרכיב קבוע לכולם, והסדר נשאר כשהיה.
    """
    features = measurements.get(track["uid"])
    size = (audio.bigness(features) / 100.0 if audio.measured(features)
            else NEUTRAL_SIZE)
    return (RANK_TASTE * taste_of(track, learned)
            + RANK_WORK * (1.0 if track.get("work_verified") else 0.0)
            + RANK_TRAILER * search_module.trailer_strength(track)
            + RANK_SIZE * size)


def _rank_breakdown(track: dict, learned: dict | None, features: dict | None) -> str:
    """הדירוג ורכיביו כשורה אחת, באותם משקלים שקבעו את הסדר בפועל."""
    measurements = st.session_state.get("bigness", {})
    score = rank_score(track, learned or {}, measurements)
    size = audio.bigness(features) if audio.measured(features) else None
    return (f"rank {score:.3f} · "
            f"taste {round(taste_of(track, learned or {}) * 100)}% · "
            + ("verified in catalogue" if track.get("work_verified")
               else "not verified in catalogue")
            + f" · trailer {search_module.trailer_strength(track):.2f} · "
            + (f"loudness {size}" if size is not None else "not measured yet"))


def sorted_by(tracks: list, sort_by: str, learned: dict) -> list:
    """הסדר המבוקש, מחושב על הנתונים שיש **ברגע זה**."""
    ranked = list(tracks)
    measurements = st.session_state.get("bigness", {})

    def measured_size(track):
        features = measurements.get(track["uid"])
        # במיון המפורש לפי גודל, "טרם נמדד" באמת יורד לתחתית ולא מתחזה למדוד
        return audio.bigness(features) if audio.measured(features) else -1

    if sort_by == SORT_BEST:
        # ברירת המחדל. `score` נשאר רק כשובר שוויון
        ranked.sort(key=lambda t: (round(rank_score(t, learned, measurements), 4),
                                   t.get("score", 0)), reverse=True)
    elif sort_by == SORT_LOUDNESS:
        ranked.sort(key=lambda t: (measured_size(t), t.get("score", 0)), reverse=True)
    elif sort_by == SORT_RELEVANCE:
        ranked.sort(key=lambda t: t.get("score", 0), reverse=True)
    elif sort_by == SORT_NEWEST:
        ranked.sort(key=lambda t: search_module.release_year(t), reverse=True)
    elif sort_by == SORT_SHORTEST:
        ranked.sort(key=lambda t: t.get("duration_sec", 0))
    elif sort_by == SORT_LONGEST:
        ranked.sort(key=lambda t: t.get("duration_sec", 0), reverse=True)
    elif sort_by == SORT_ARTIST:
        ranked.sort(key=lambda t: t.get("artist", "").lower())
    return ranked


def ordered_display(tracks: list, sort_by: str, same_work_only: bool,
                   learned: dict) -> list:
    """הסדר נקבע פעם אחת ונשאר — הליבה של תיקון "הכל קופץ".

    מפתח המיון הראשי תלוי במדידות האודיו שממשיכות לזרום מהדפדפן אחרי
    שהתוצאות כבר על המסך, וגם ב-`learned` שמשתנה בכל לחיצת ❤️. כשהוא חושב
    מחדש בכל rerun, נמדד ש-20 מתוך 20 השורות הנראות משנות מיקום ברגע
    שהמדידות חוזרות, ושלחיצת ❤️ אחת דוחפת שלושה שירים אל מעבר ל-20
    המוצגים — כלומר הם "נעלמים". גרוע מכך: ל-`st.audio` אין `key`, ולכן
    זהות הנגן היא מיקומית, ואחרי שינוי סדר הצליל של שיר אחד יושב על
    הכרטיס של שיר אחר (נמדד בדפדפן: הנגן המנגן עבר משורה 1 לשורה 3).

    לכן הסדר נשמר כרשימת uid ומחושב מחדש רק כשמשתנה החתימה — בורר המיון,
    הפילטר, או חיפוש חדש. הדירוג לפי טעם לא בוטל, רק רגע ההחלה שלו הוקפא;
    `resort_button` מחזיר את השליטה למשתמש.
    """
    signature = (sort_by, same_work_only, st.session_state["result_generation"])
    if st.session_state["order_signature"] != signature:
        st.session_state["order_signature"] = signature
        st.session_state["display_order"] = [t["uid"] for t in
                                             sorted_by(tracks, sort_by, learned)]
    return apply_order(tracks, st.session_state["display_order"])


def apply_order(tracks: list, order: list) -> list:
    """מסדר לפי רשימת uid שמורה. מה שנעלם יורד, מה שחדש נוסף בסוף.

    "חדש" קורה כשהמשתמש לוחץ "עוד קאברים לשיר הזה" באמצע רשימה קיימת;
    "נעלם" קורה בחסימת אמן. בשני המקרים שאר השורות לא זזות.
    """
    by_uid = {t["uid"]: t for t in tracks}
    kept = [by_uid[uid] for uid in order if uid in by_uid]
    known = set(order)
    return kept + [t for t in tracks if t["uid"] not in known]


def resort_button(display: list, sort_by: str, learned: dict):
    """מיישם את מה שנלמד מאז — ביוזמת המשתמש, ולא באמצע האזנה.

    בלי זה ההקפאה הייתה מסתירה את הלמידה עד החיפוש הבא. הכפתור אומר מראש
    כמה שורות יזוזו, כדי שהתזוזה לא תהיה הפתעה.
    """
    fresh = [t["uid"] for t in sorted_by(display, sort_by, learned)]
    current = [t["uid"] for t in display]
    moving = sum(1 for old, new in zip(current, fresh) if old != new)

    # הכפתור מצויר תמיד, גם כשאין מה לסדר — כפתור שמופיע ונעלם מעל הרשימה
    # דוחף את כל מה שמתחתיו (נמדד: 17px בכל לחיצת ❤️), וזה בדיוק מה שמזיז
    # את המקום שבו המשתמש היה
    label = (f"Re-sort by {sort_by} — {moving} tracks will move" if moving
             else "Order is up to date")
    if st.button(label, key="btn_resort", disabled=not moving,
                 icon=":material/sort:", type="tertiary",
                 help="The order is frozen while you browse so the list never "
                      "shifts mid-listen. This applies what has been learned "
                      "since — new loudness measurements and loves."):
        st.session_state["display_order"] = fresh
        st.rerun()


# ---------- הצגת שיר בודד ----------

# מדרגות העוצמה, וכל אחת עם צבע המד שלה. הערכים מגיעים מטבלת הטוקנים
# בהנדאוף (`score >= 70 -> #FFB020`, `40-69 -> #C3C8D4`, `< 40 -> #8A91A3`),
# והספים עצמם הם אלה של `audio.py` ולא מספרים חדשים. ענבר שמור ל"גדול"
# בלבד — אקסנט שמופיע על כל שורה מפסיק לסמן משהו.
SCORE_TIERS = (
    (audio.BIG_VERSION_THRESHOLD, "#FFB020", "big"),
    (audio.MID_VERSION_THRESHOLD, "#C3C8D4", "mid"),
    (0, "#8A91A3", "calm"),
)
ARTWORK_SIZE = 52
# צבע ותווית לשורה שעוד לא נמדדה. רצועה ריקה ולא תג: המד הוא העמודה
# שקוראים לאורכה, ותג בגובה אחר באמצע היה שובר את הקו.
METER_IDLE = "#1E2230"


def _loudness_meter(features: dict | None):
    """העוצמה כמספר גדול שקוראים מיד, מעל רצועה שמשווה בין השורות.

    זה הנתון שהאפליקציה קיימת בשבילו. ההנדאוף נימק את הצורה כ-"a meter
    you read across rows instead of a badge you decode", והרצועה עדיין
    עושה בדיוק את זה — היא עונה על "לעומת מי". מה שהשתנה הוא שהמספר עלה
    מעליה ולגודל שקוראים מיד, לפי רפרנס שהמשתמש הביא: הוא התשובה המדויקת
    ל"כמה", והיא לא צריכה להיות הדבר הקטן בשורה.

    יישור הספרות בין השורות בא מ-`font-variant-numeric: tabular-nums`
    שיושב על כל אזור התוכן, ולא מגופן מונו כפי שהיה קודם: בלעדיו "9"
    ו-"87" מתחילים במקומות שונים והעין קופצת.
    """
    if audio.measured(features):
        score = audio.bigness(features)
        color = next(c for threshold, c, _ in SCORE_TIERS if score >= threshold)
        pct = max(0, min(100, int(score)))
        st.html(
            "<div class='ts-meter'>"
            f"<span class='ts-meterval' style='color:{color}'>{score}</span>"
            f"<div class='ts-metertrack'><div class='ts-meterfill'"
            f" style='width:{pct}%;background:{color}'></div></div>"
            "</div>")
        return

    # לא נמדד: אותה רצועה בדיוק, ריקה, עם תווית mono במקום המספר. שורה
    # שאין לה עדיין ציון חייבת לתפוס את אותו גובה ואת אותו רוחב, אחרת
    # הרשימה קופצת בכל פעם שמדידה מסתיימת.
    label = ("server" if (features or {}).get("error") == "cors_failed"
             else "\u2013")
    st.html(
        "<div class='ts-meter'>"
        f"<span class='ts-meterval ts-meteridle'>{label}</span>"
        f"<div class='ts-metertrack'></div>"
        "</div>")


def _artwork(track: dict):
    """עטיפת האלבום — סימן הזיהוי המהיר ביותר בכלי מוזיקה.

    הכתובת חוזרת מ-iTunes ומ-Deezer מאז ומעולם (`search.py`) ופשוט לא הוצגה.
    `st.image` מעביר את ה-URL לדפדפן כמו שהוא, ולכן הטעינה היא של המשתמש ולא
    של השרת — מה שחשוב כאן, כי השרת חסום מול חלק מהחנויות.
    """
    art = track.get("artwork")
    if art:
        st.image(art, width=ARTWORK_SIZE)
    else:
        # ריבוע ולא כלום: בלעדיו כל השורות מתחתיו מתיישרות אחרת
        st.html(
            f"<div class='ts-art-blank' style='width:{ARTWORK_SIZE}px;"
            f"height:{ARTWORK_SIZE}px;'></div>")


def render_track(track: dict, index: int, learned: dict | None = None):
    uid = track["uid"]
    features = st.session_state.get("bigness", {}).get(uid)
    evidence = st.session_state.get("evidence", {}).get(uid) or []
    indicators = search_module.trailer_indicators(track)

    # שורה אחת לכל תוצאה, ולא כרטיס עם מסגרת. Streamlit לא מכווץ עמודות
    # בטלפון אלא **עורם** אותן לרוחב מלא, כך שכל תוצאה הפכה לשמונה בלוקים
    # נפרדים — עשרים תוצאות היו 160 בלוקים, ומכאן "לא עובד בפלאפון".
    # מכולה אופקית נשענת על flex ולכן היא נשארת שורה בשני הרוחבים.
    # מפתח המכולה נושא את דור התוצאות ולא רק את ה-uid.
    #
    # מכולה עם `key` מקבלת זהות יציבה, ולכן חיפוש חדש שיצר מפתחות אחרים
    # לא הפיל את השורות של החיפוש הקודם: הן נשארו תלויות **מעל** התוצאות
    # החדשות, על הכפתורים שלהן. בצילום מסך אחד נראו חמש-עשרה שורות של
    # "The Sound of Silence" מעל עשרים שורות תקינות של "When I Need You",
    # כלומר יותר שורות ממה שהכותרת עצמה הצהירה עליהן.
    #
    # הדור כבר קיים ב-session state בשביל שומר הגלילה, והוא עולה בכל
    # החלפת תוצאות. הוספתו כאן מבטיחה שאף מפתח מהחיפוש הקודם אינו קיים
    # בעץ החדש, ולכן אין לשריד במה להיאחז.
    #
    # אין על זה בדיקה, ולא במקרה: `AppTest` בונה את העץ של הריצה הנוכחית
    # בלבד ואינו חושף כלל מפתחות של מכולות (נבדק), ולכן כל בדיקה שנכתבה
    # כאן עברה גם בלי התיקון. אימות אמיתי הוא שני חיפושים רצופים בדפדפן.
    #
    # הוא נכנס **אחרי** התחילית ולא לפניה: כללי ה-CSS מתאימים לפי
    # `[class*="st-key-trow_"]`, ולכן התחילית חייבת להישאר בהתחלה.
    #
    # רק המכולות, לא הכפתורים: `btn_favorite_<uid>` הוא הזהות של הפעולה
    # על הטראק הזה, ו-`bigness[uid]` הוא המדידה שלו. שניהם חייבים לשרוד
    # חיפוש חדש, בעוד שהמכולה היא בדיוק מה שצריך להיעלם איתו.
    row_key = f"{st.session_state.get('result_generation', 0)}_{uid}"

    row = st.container(key=f"trow_{row_key}", horizontal=True, wrap=False,
                       vertical_alignment="center", gap="medium")
    with row:
        col_art = st.container(width=ARTWORK_SIZE)
        col_play = st.container(key=f"tplay_{row_key}", width="content")
        col_main = st.container(key=f"tmain_{row_key}", width="stretch")
        col_tags = st.container(key=f"ttags_{row_key}", width="content")
        col_meter = st.container(key=f"tmeter_{row_key}", width="content")
        col_acts = st.container(key=f"tacts_{row_key}", width="content",
                                horizontal=True, vertical_alignment="center")

    with col_art:
        _artwork(track)

    with col_play:
        # כפתור הנגינה יושב בשורה עצמה ולא בשורת פעולות נפרדת: הוא הפעולה
        # שנעשית הכי הרבה פעמים, והוא צריך להיות ליד העטיפה שמזהים לפיה
        if track.get("preview_url"):
            audio_player(track["preview_url"], ident=uid, track=track)
        else:
            st.html("<div class='ts-player ts-noplay'"
                    " title='No preview available'></div>")

    with col_main:
        # האמן ראשון ובולט: בחיפוש קאברים לשיר אחד, מה שמבדיל בין התוצאות
        # הוא מי ביצע — לא שם השיר, שחוזר על עצמו בכל השורות.
        # שם השיר הוא קישור ל-YouTube Music: התצוגה המקדימה היא 30 שניות,
        # וזה המסלול לשמוע את הגרסה המלאה. Streamlit מוסיף target="_blank"
        # ו-rel="noopener" לקישורי markdown, ולכן האפליקציה לא ננטשת.
        st.html(f"<div class='ts-rowartist'>{html.escape(track['artist'])}</div>")

        meta = [part for part in (
            track.get("genre"),
            str(track.get("year") or "") or None,
            f"{int(track.get('duration_sec', 0) // 60)}:{int(track.get('duration_sec', 0) % 60):02d}"
            if track.get("duration_sec") else None,
        ) if part]
        # `st.html` ולא `st.markdown`: נמדד בדפדפן שמכולת ה-markdown נותנת
        # לתוכן גובה קבוע של 20px, והשורה הבאה (תגי הסימנים) נכנסה לתוכה —
        # תשע פיקסלים של חפיפה על כל שורת תוצאה.
        st.html(
            f"<div class='ts-rowmeta'>"
            f"<a href='{youtube_music_url(track['artist'], track['track'])}'"
            f" target='_blank' rel='noopener'>{html.escape(track['track'])}</a>"
            + ((" · " + html.escape(" · ".join(meta))) if meta else "")
            + "</div>")

        for item in evidence[:2]:
            st.caption(f":material/movie: [{item['title'][:70]}]({item['url']}) — {item['channel']}")
        if track.get("origin_track"):
            st.caption(f"Cover of: {track['origin_track']}")

    with col_tags:
        # הסיבה לדירוג, גלויה: `trailer_strength` נספר בדיוק מהרשימה הזו.
        # עמודה משלהם ולא שורה שלישית מתחת לכותרת — אחרת השורה מתארכת
        # ב-24px (נמדד) ומפסיקה להיות שורה שסורקים בה.
        # שניים לכל היותר. נמדד ברוחב 1080: שלושה תגים (SOUNDTRACK,
        # CINEMATIC) תפסו 260px ודחסו את שם האמן ל-16px. השאר נשארים
        # ב-⋯ דרך פירוק הדירוג, שם ממילא מפורטת הסיבה המלאה.
        # תג מוצהר אחד (ענבר, מהכותרת) ותג נמדד אחד (אפור, מהמדידה).
        # אפור בכוונה: מערכת העיצוב שומרת את הענבר לפעולה הראשית ולדרגת
        # ה"ענק", ואקסנט על כל שורה מפסיק לסמן משהו.
        # תקציב שני התגים נשמר: כשיש תג נמדד הוא לוקח את המקום השני,
        # וכשאין — שני המוצהרים חוזרים כפי שהיו. פירוק הדירוג המלא יושב
        # ממילא ב-⋯, ולכן מה שיורד מכאן לא הולך לאיבוד.
        _measured_tag = tags_module.primary_tag(features)
        _declared = indicators[:1] if _measured_tag else indicators[:2]
        _chips = [f"<span class='ts-tag'>{html.escape(sign.upper())}</span>"
                  for sign in _declared]
        if _measured_tag:
            _chips.append("<span class='ts-tag ts-tag-heard'>"
                          f"{html.escape(_measured_tag.upper())}</span>")
        if _chips:
            st.html("<div class='ts-tags'>" + "".join(_chips) + "</div>")

    with col_meter:
        _loudness_meter(features)
        if learned and learned.get("count"):
            # למה הטראק הזה עלה: אחרת שינוי הסדר נראה שרירותי
            fit = taste_of(track, learned)
            if fit >= TASTE_BADGE_THRESHOLD:
                st.html(f"<div class='ts-fit'>{round(fit * 100)}% your taste</div>")

    with col_acts:
        favorited, rejected = is_favorite(track), is_rejected(track)
        if st.button("", key=f"btn_favorite_{uid}",
                     icon=":material/favorite:" if favorited else ":material/favorite_border:",
                     type="primary" if favorited else "secondary",
                     help="Remove from Loved" if favorited else
                          "Save to Loved — the ranking learns what you like"):
            toggle_favorite(track)
            st.rerun()
        # דוגמה שלילית שווה יותר מדוגמה חיובית נוספת: היא נותנת ללמידה כיוון,
        # בעוד שעוד לייק רק מהדק מרכז כובד שכבר ידוע
        if st.button("", key=f"btn_reject_{uid}", icon=":material/thumb_down:",
                     type="primary" if rejected else "secondary",
                     help="Undo" if rejected else
                          "Not this — the ranking learns to move away from this style"):
            toggle_rejection(track)
            st.rerun()

        # תפריט אחד לכל מה שנדיר: קודם כל פעולה תפסה כפתור משלה בכל שורה,
        # ושש שורות טקסט אפור נאבקו על אותה תשומת לב
        with st.popover("", icon=":material/more_horiz:", width=54):
            st.caption(f"More like **{track['track']}**")
            if st.button("More covers of this song", key=f"more_covers_{uid}",
                         icon=":material/library_music:", use_container_width=True):
                st.session_state["similar_of"] = ("covers", track)
                st.rerun()
            if st.button("More in this style", key=f"more_style_{uid}",
                         icon=":material/palette:", use_container_width=True,
                         help="By this track's genre and artist. Browser "
                              "measurement then sorts what comes back by loudness."):
                st.session_state["similar_of"] = ("style", track)
                st.rerun()

            st.divider()
            details = [f"source: {track['source']}",
                       f"relevance: {track.get('score', 0)}"]
            if track.get("catalog_source"):
                details.append(f"found via: {track['catalog_source']}")
            if track.get("album"):
                details.append(f"album: {track['album']}")
            st.caption(" · ".join(details))
            # פירוק הדירוג: "למה זה כאן" נשאל בפועל, והתשובה דרשה חישוב
            # ידני. כאן היא גלויה — וגם רואים מיד אם גרסה שאמורה להיות
            # מאומתת בקטלוג אינה מאומתת.
            st.caption(_rank_breakdown(track, learned, features))
            if audio.measured(features):
                st.caption(audio.describe(features))
            st.divider()
            if st.button("Block artist", key=f"btn_block_{uid}",
                         icon=":material/block:", use_container_width=True):
                st.session_state["blacklist"].add(clean_artist_name(track["artist"]).lower())
                storage.save_blacklist(st.session_state["blacklist"], SUBJECT)
                st.session_state["candidates"] = apply_blacklist(st.session_state["candidates"])
                st.toast(f"Blocked '{track['artist']}'")
                st.rerun()


# ---------- מסך חיפוש מאוחד ----------

_audio_behaviour()
_keep_scroll_position()

# סרגל עליון שמופיע **רק בטלפון** (ראו ה-media query ב-CSS): שם ה-rail
# מתקפל מאחורי כפתור ההמבורגר של Streamlit, ובלעדיו אין על המסך שום זהות
# ושום מונה. בדסקטופ ה-rail כבר נושא את שניהם, ולכן שם הוא מוסתר.
with st.container(key="appbar", horizontal=True, vertical_alignment="center"):
    st.html("<div class='ts-mark'></div>")
    st.html("<span class='ts-word ts-word-inline'>COVER LOVER</span>")
    st.container(width="stretch")
    st.html(f"<span class='ts-navcount'>{len(st.session_state['favorites'])}"
            " loved</span>")

# מסך ולא סרגל. `st.stop()` ולא הסתרה ב-CSS: זה מסך אחר, ואין סיבה
# לשלם על רינדור של כל התוצאות מאחוריו. מה שנשמר לפני העצירה הוא מצב
# הפקדים — ראו `_remember_screen_state`.
_nav = st.session_state["rail_nav"]
# שאילתה שממתינה פירושה שמישהו ביקש לראות תוצאות; מסך אחר היה בולע
# אותה בשקט, כי השדות שהיא ממלאת אינם נוצרים שם בכלל
if st.session_state.get("pending_fields"):
    _nav = st.session_state["rail_nav"] = NAV_DISCOVER
if _nav in (NAV_LOVED, NAV_SETTINGS):
    _remember_screen_state()
    if _nav == NAV_LOVED:
        _loved_screen()
    else:
        _settings_screen()
    st.stop()

_restore_screen_state()

_pending = st.session_state.pop("pending_fields", None)
if _pending:
    _title, _artist, _mode, _auto_run = _pending
    st.session_state["cover_title"], st.session_state["cover_artist"] = _title, _artist
    if _mode:
        st.session_state["search_mode"] = _mode
    if _auto_run:
        st.session_state["auto_run"] = True

RECENT_ROLLS = 5


def roll_famous_song():
    """ממלא את השדות בשיר מוכר — **בלי להריץ חיפוש**.

    ההגרלה והחיפוש הופרדו לבקשת המשתמש: לחיצה חוזרת על הכפתור מגלגלת
    שירים עד שאחד מוצא חן, והחיפוש (שהוא היקר — קריאות רשת לקטלוג
    ולחנויות) רץ רק כשלוחצים על "Find covers". קודם כל הגרלה יצאה
    לרשת מיד, כלומר עשר גלגולים היו עשרה חיפושים מלאים שאיש לא ביקש.

    הבריכה היא `classics.famous_pool()` — נתוני המצעד מ-1960 ואילך ועוד
    רשימות הפופ והרוק. פופולריות במצעד היא הקירוב ל"סביר שיש לו קאבר";
    בדיקה אמיתית הייתה קריאת רשת לכל מועמד, והיא הופכת לחיצה מיידית
    להמתנה.
    """
    pool = classics_module.famous_pool()
    recent = st.session_state["recent_rolls"]
    # בלי זה שתי הגרלות רצופות מחזירות לפעמים את אותו שיר, וזה נראה תקול
    fresh = [entry for entry in pool
             if (entry["artist"], entry["track"]) not in recent] or list(pool)
    choice = random.choice(fresh)

    st.session_state["recent_rolls"] = (
        recent + [(choice["artist"], choice["track"])])[-RECENT_ROLLS:]
    queue_fields(choice["track"], choice["artist"], mode=MODE_SONG)


# שדה חיפוש אחד ולא שלוש עמודות עם תווית מעל כל אחת: המסגרת היא של
# המכולה (`.st-key-searchbar` ב-CSS), והשדות שקופים בתוכה — כך זה נקרא
# כרכיב אחד במקום שלושה טפסים נפרדים.
# `wrap=True`: בדסקטופ הכל נכנס לשורה אחת ממילא, ובטלפון הכפתורים יורדים
# לשורה שנייה במקום להידחס עד שהטקסט נחתך
searchbar = st.container(key="searchbar", horizontal=True, wrap=True,
                         vertical_alignment="center")
with searchbar:
    st.html("<span class='ts-searchglyph'></span>")
    cover_title = st.text_input(
        "Song", key="cover_title", placeholder="Song or artist",
        label_visibility="collapsed",
        help="A song name or an artist name, and one search mode: covers of a "
             "song (from the catalogue and the stores), covers of an artist's "
             "whole catalogue, or a free search with filters.")

    # האמן כ-chip ולא כשדה שני קבוע. ברוב החיפושים הוא נקבע מהגרלה, מלחיצה
    # על שיר במצעדים או מהצעת השלמה — כלומר הוא כבר **ידוע**, ושדה ריק
    # שני באמצע השורה רק גזל את הרוחב משם השיר. כשהוא ריק השדה חוזר.
    #
    # השדה נוצר **תמיד**, וכשיש ערך הוא מוסתר ב-CSS במקום לא להיווצר.
    # נמדד: Streamlit מנקה מ-`session_state` מפתח של widget שהפסיק
    # להיווצר, ולכן הגרסה שהחליפה את השדה ב-chip איבדה את שם האמן בריצה
    # שאחרי — הפלייליסט נשמר עם `origin.artist` ריק. `display:none`
    # מוציא את השדה גם מסדר ה-Tab, ולכן אין כאן פקד נסתר שאפשר להגיע אליו.
    #
    # בלי מכולה עוטפת: ה-`key` של ה-widget מפיק `st-key-cover_artist`
    # על המכולה שלו ממילא, וה-CSS מסתיר אותו לפי נוכחות ה-chip. מכולה
    # נוספת רק הוסיפה גובה, ובטלפון היא מתחה את שורת החיפוש (נמדד).
    _artist_value = (st.session_state.get("cover_artist") or "").strip()
    cover_artist = st.text_input(
        "Original artist", key="cover_artist",
        placeholder="Original artist (optional)",
        label_visibility="collapsed",
        help="Disambiguates: 'Sweet Dreams' is both a 1955 country "
             "standard and Eurythmics 1983.")

    if _artist_value:
        chip = st.container(key="artistchip", horizontal=True,
                            vertical_alignment="center")
        with chip:
            st.html(f"<span class='ts-chiptext'>{html.escape(_artist_value)}</span>")
            if st.button("", key="clear_artist", type="tertiary",
                         icon=":material/close:", help="Clear the artist"):
                queue_fields(st.session_state.get("cover_title", ""), "")

    # "Surprise me" ולא אימוג'י קובייה. הכפתור הקודם היה 🎲 בתווית, והוא
    # רץ שני סבבים של באגי רינדור (icon=":material/casino:" ואז icon="🎲"
    # יצאו שניהם כנקודה כתומה). תווית מילולית פותרת את זה מהשורש, וגם
    # אומרת מה הכפתור עושה — דבר שאימוג'י בודד לא עשה.
    if st.button("Surprise me", key="btn_dice",
                 help="Drops a well-known song into the field — press again "
                      "for another one. Nothing is searched until you press "
                      "Find covers. The better known the song, the likelier "
                      "someone has already covered it."):
        roll_famous_song()

    _clicked_search = st.button("Find covers", key="btn_search", type="primary")


# שורת המצבים: מצב החיפוש משמאל, מיון ופילטרים מימין. הפילטרים ירדו
# מאקספנדר ברוחב חצי-מסך ל-popover בשורה הזו — שני פסים ריקים בין שורת
# החיפוש לתוצאות נראו כמו שני כרטיסים שלא נטענו, והם גם דחפו את התוצאות
# (מה שהמשתמש בא בשבילו) מתחת לקפל.
mode_row = st.container(key="moderow", horizontal=True, wrap=True,
                        vertical_alignment="center")
with mode_row:
    # בלי `default=`: Streamlit אוסר על widget לקבל גם ערך ב-session_state
    # וגם ברירת מחדל, ו-`_restore_screen_state` כותב לשם בחזרה ממסך אחר.
    # ערך ההתחלה מגיע מ-`_init_state` ממילא.
    search_mode = st.segmented_control(
        "Search mode", SEARCH_MODES, key="search_mode",
        label_visibility="collapsed",
        help=f"{MODE_SONG}: merges the official cover catalogue "
             "(SecondHandSongs/MusicBrainz) with a store search for "
             f"'Epic/Trailer/Cinematic' tracks. {MODE_ARTIST}: finds the "
             "titles most associated with the artist and pulls covers for "
             f"each. {MODE_FREE}: a broad search driven by the filters, "
             "without pinning to one work.")
    # `segmented_control` מחזיר None כשהמשתמש מבטל את הבחירה בלחיצה חוזרת.
    # בלי הנפילה חזרה, אותה לחיצה הייתה מרוקנת את מצב החיפוש והשאילתה
    # הבאה הייתה נופלת לענף שגוי.
    search_mode = search_mode or MODE_SONG

    st.container(width="stretch")
    st.html("<span class='ts-sortlabel'>Sort</span>")
    sort_by = st.selectbox("Sort", SORT_OPTIONS, key="sort_by",
                           label_visibility="collapsed")

    _active_filters = 0
    with st.popover("Filters", icon=":material/tune:"):
        # לכל פקד `key`: בלי זה מעבר למסך Loved וחזרה היה מאפס את
        # הפילטרים, כי Streamlit מוחק מצב של widget שלא נוצר בריצה
        # (ראו `SCREEN_SAFE_KEYS`)
        style_filter = st.selectbox("Style / genre", [ALL, *STYLES],
                                    key="filter_style")
        length_filter = st.selectbox(
            "Track length", [ALL, LENGTH_SHORT, LENGTH_MEDIUM, LENGTH_LONG],
            key="filter_length")
        recency = st.selectbox("Released", list(RECENCY_OPTIONS),
                               key="filter_recency")
        # המסנן היחיד שפועל כאן ולא בחנות: לחנות אין מושג איך טראק נשמע.
        # הוא מסנן את מה שכבר הוצג, ולכן הוא עובד רק על שורות שהדפדפן
        # הספיק למדוד — שורה שטרם נמדדה עוברת, ולא נעלמת בשקט.
        sound_filter = st.selectbox(
            "Sounds like", [ALL, *tags_module.TAGS], key="filter_sound",
            help="From the measurement that runs in your browser, not from "
                 "the title. Rows that have not been measured yet stay.")
        prefer_new = st.checkbox(
            "Prefer newer with a high score", value=True, key="filter_prefer_new",
            help="A freshness bonus that fades from 25 to zero over five years.")
        fresh_only = st.checkbox(
            "Unheard only", value=False, key="filter_fresh_only",
            help="Skips results already shown in this session, to bring up "
                 "new material.")
        same_work_only = st.checkbox(
            "Verified same work only", value=False, key="filter_same_work",
            help="A store search matches by name alone, so \"I'm Sorry\" also "
                 "returns different songs with that title. This keeps only "
                 "recordings the catalogue (SecondHandSongs/MusicBrainz) "
                 "identifies as versions of the same work. The cost: trailer "
                 "versions from production libraries are usually not in the "
                 "catalogue, and they disappear.")

        if st.session_state.get("search_mode") == MODE_SONG:
            st.caption("Style only affects the part that comes from "
                       "the store search. The official catalogue "
                       "(SecondHandSongs/MusicBrainz) does not support "
                       "filtering like that, so its versions always appear.")

    _active_filters = sum([
        style_filter != ALL, length_filter != ALL, sound_filter != ALL,
        RECENCY_OPTIONS[recency] != 0, fresh_only, same_work_only,
    ])
    if _active_filters:
        # המונה על התווית הוא מה שמונע פילטר ששכחו עליו: popover סגור
        # נראה זהה בין "בלי סינון" ל"שני פילטרים פעילים"
        st.html(f"<span class='ts-filtercount'>{_active_filters}</span>")

filters = {"style": style_filter, "length": length_filter}


ARTIST_PREVIEW_COUNT = 20


def _artist_preview_titles(artist: str) -> list[str]:
    """עד 20 השירים המזוהים ביותר עם האמן, זול (קריאת iTunes אחת) ומקוצ'ר.

    לחיצה על אמן באינדקס המצעדים לא צריכה להריץ מיד חיפוש קאברים יקר
    (עד 8 חיפושים מקבילים) לפני שהמשתמש בכלל ראה אילו שירים נבחרו לו.
    הקאש לפי שם מנורמל מונע קריאת iTunes חוזרת בכל rerun (checkbox, מדידת
    אודיו וכו׳).
    """
    key = search_module.normalize_artist(artist)
    if st.session_state["artist_preview_query"] != key:
        st.session_state["artist_preview_query"] = key
        search_module.reset_errors()
        with st.spinner(f"Finding songs by {artist}..."):
            st.session_state["artist_preview_titles"] = covers_module.artist_top_titles(
                artist, limit=ARTIST_PREVIEW_COUNT)
    return st.session_state["artist_preview_titles"]


def _entry_grid(entries: list[dict], key_prefix: str):
    """רשת כפתורים משותפת לאמנים ולשירים, מכל אחד משלושת מקורות האינדקס.

    לחיצה על אמן ממלאת את שדה האמן וקובעת מצב "קאברים לאמן" — תצוגה מקדימה
    זולה של שירי האמן מוצגת לפני שחיפוש הקאברים היקר רץ (ראו
    `_artist_preview_titles`). לחיצה על שיר ממלאת שיר+אמן, קובעת מצב
    "קאברים לשיר" ומריצה אוטומטית. שלושת המקורות (קלאסיקות סטטיות, רשימת
    בילבורד, מצעד מיובא) שונים בנתונים אבל זהים בהתנהגות — לכן רכיב רינדור
    אחד במקום שלושה כמעט-זהים.
    """
    is_song = any(entry["kind"] == "song" for entry in entries)
    per_row = 2 if is_song else 4
    for row_start in range(0, len(entries), per_row):
        columns = st.columns(per_row)
        for offset, (column, entry) in enumerate(
                zip(columns, entries[row_start:row_start + per_row])):
            rank = entry.get("rank")
            # המפתח נגזר מהמיקום ברשימה ולא מהשם: שני שירים שונים בשם
            # "Rockstar" באותה שורה מייצרים מפתח כפול ומפילים את העמוד.
            key = f"{key_prefix}_{row_start + offset}"
            if entry["kind"] == "artist":
                name = entry["artist"]
                label = f"{rank}. {name}" if rank else name
                clicked = column.button(label, key=key, use_container_width=True)
            else:
                full_label = (f"{rank}. " if rank else "") + f"{entry['track']} — {entry['artist']}"
                # חיתוך רך ב-CSS ולא קשה בפייתון: `[:60]` חתך באמצע מילה
                # ("Barbra Streis"), בעוד ש-ellipsis נותן שלוש נקודות
                clicked = column.button(full_label, key=key, help=full_label,
                                        use_container_width=True)
            if clicked:
                # האינדקס ארוך (עד 120 שירים), והצעד הבא של המשתמש — תוצאות
                # או תצוגת השירים המקדימה — מרונדר במסך אחר. חזרה ל-Discover
                # היא מה שמראה לו את מה שהוא בדיוק ביקש.
                st.session_state["rail_nav"] = NAV_DISCOVER
                if entry["kind"] == "artist":
                    # לא auto_run: קודם מוצגת תצוגה מקדימה זולה של שירי האמן
                    # (ראו את המקטע אחרי רדיו "סוג חיפוש") — חיפוש הקאברים
                    # המלא יקר ולא צריך לרוץ לפני שהמשתמש בחר מה לחפש בפועל
                    queue_fields(artist=entry["artist"], mode=MODE_ARTIST)
                else:
                    queue_fields(entry["track"], entry["artist"], mode=MODE_SONG, auto_run=True)


def _classics_entries(category: str) -> list[dict]:
    """קלאסיקות לפי ז'אנר או עשור, 1950–2020 — רשימה סטטית, לא מצעד חי.

    מצעד Deezer חי הציג טרנדים עדכניים שהמשתמש לרוב לא מזהה. הרשימות כאן
    קבועות בקוד: הז'אנרים אצורים ב-`classics.py`, והעשורים מגיעים מנתוני
    Billboard Hot 100 ההיסטוריים דרך `chart_data` (ראו `tools/build_charts.py`).
    """
    source = classics_module.CATEGORIES.get(category, ())
    return [{"kind": "song", "artist": entry["artist"], "track": entry["track"],
            "rank": index + 1} for index, entry in enumerate(source)]


def _goat_entries(filter_text: str) -> list[dict]:
    ranks = {name: index + 1 for index, name in enumerate(artists_module.GREATEST_ARTISTS)}
    return [{"kind": "artist", "artist": name, "rank": ranks.get(name)}
            for name in artists_module.search_artists(filter_text)]


def _imported_entries(chart: dict) -> list[dict]:
    if chart["kind"] == billboard_module.ARTISTS:
        return [{"kind": "artist", "artist": e["artist"], "rank": e.get("rank")}
                for e in chart["entries"]]
    return [{"kind": "song", "artist": e["artist"], "track": e["track"], "rank": e.get("rank")}
            for e in chart["entries"]]


def _charts_panel():
    """אינדקס המצעדים כמסך, ולא כאקספנדר באמצע הדף.

    קודם הוא היה `st.expander` שדרש מפתח נגזר-מונה רק כדי להיסגר אחרי
    לחיצה (ל-`st.expander` אין מצב פתוח/סגור ב-`session_state`, והעברת
    `expanded=False` כשהוא כבר False אינה סוגרת דבר). עכשיו זה פריט ניווט
    ב-rail: הוא מוצג כשבוחרים בו, והלחיצה על שיר מחזירה ל-Discover — מה
    שמייתר את הפטנט לגמרי.
    """
    st.html("<h2 class='ts-h2'>Charts</h2>")
    st.html("<div class='ts-lede'>A starting point for a search: clicking an "
            "artist runs 'Covers of an artist', clicking a song runs 'Covers "
            "of a song'. Chart position does not affect result ranking — "
            "there, what is measured from the audio decides.</div>")

    imported = storage.load_charts()
    sources = [SOURCE_CLASSICS,
               f"{SOURCE_GOAT} ({len(artists_module.GREATEST_ARTISTS)})"]
    sources += [f"Imported: {chart['title']}" for chart in imported.values()]
    source = st.radio("Source", sources, horizontal=True, key="index_source",
                      label_visibility="collapsed")

    entries, key_prefix = [], ""
    if source.startswith(SOURCE_CLASSICS):
        # selectbox ולא radio: שלוש-עשרה קטגוריות בשורה אחת אינן קריאות
        category = st.selectbox("Category", list(classics_module.CATEGORIES),
                                key="classics_category")
        entries = _classics_entries(category)
        key_prefix = "classic"
        st.caption(f"{len(entries)} songs · decades are ranked by actual "
                   "performance on the historical Billboard Hot 100, genres by "
                   "curated lists. At most two songs per artist in each "
                   "category, so the same artist does not repeat.")

    elif source.startswith(SOURCE_GOAT):
        artist_filter = st.text_input("Filter the list", key="artist_filter",
                                      placeholder="beatles")
        entries = _goat_entries(artist_filter)
        key_prefix = "goat"
        if not entries:
            st.caption("No artist by that name in the list. You can still type "
                       "one into the artist field.")

    else:
        chart = next((c for c in imported.values() if source.endswith(c["title"])), None)
        if not chart:
            st.caption("Chart not found. Import it again from Settings.")
        else:
            entries = _imported_entries(chart)
            key_prefix = f"imp_{chart['slug']}"

    if entries:
        _entry_grid(entries, key_prefix)


def _lookup_failed() -> str:
    """הודעה כשהחיפוש נכשל, במקום להציג 'לא נמצאו תוצאות'.

    חנות שהחזירה 429/503 נראתה בדיוק כמו חיפוש שלא מצא כלום, ולכן הלחיצה
    השנייה "עבדה". עכשיו יש ניסיונות חוזרים, ומה שנכשל בכל זאת נאמר במפורש.
    """
    errors = search_module.last_errors()
    if not errors:
        return ""
    unique = list(dict.fromkeys(errors))
    return "Search didn't complete: " + " · ".join(unique[:3])


if st.session_state["rail_nav"] == NAV_CHARTS:
    _charts_panel()

chosen_work = ""
if search_mode == MODE_SONG:
    with mode_row:
        _which = st.button("Which songs have this name?", key="btn_which",
                           type="tertiary", icon=":material/help_outline:")
    if _which:
        if not cover_title.strip():
            st.warning("Enter a song name")
        else:
            search_module.reset_errors()
            with st.spinner("Looking up works..."):
                st.session_state["work_candidates"] = covers_module.musicbrainz_work_candidates(
                    cover_title, cover_artist)
            st.session_state["work_query"] = search_module.track_key(
                cover_artist, cover_title)
            if not st.session_state["work_candidates"]:
                failure = _lookup_failed()
                if failure:
                    st.error(failure + " — try again")
                else:
                    st.info("No works found with that name. You can search "
                            "directly with Find covers.")

    # הבורר שייך לשאילתה שעבורה נפתר. בלי הבדיקה הזו בחירה של "Sweet
    # Dreams" שרדה הקלדה של "Yellow", ו-`work_id` של Sweet Dreams נשלח
    # לחיפוש — `find_covers` מדלגת אז על זיהוי היצירה לגמרי ומחזירה
    # גרסאות של השיר הלא נכון, בלי שום סימן למשתמש (נבדק).
    if st.session_state.get("work_query") != search_module.track_key(
            cover_artist, cover_title):
        st.session_state["work_candidates"] = []
        st.session_state["work_query"] = ""

    work_candidates = st.session_state.get("work_candidates") or []
    if work_candidates:
        # "Sweet Dreams" הוא גם סטנדרט קאנטרי מ-1955 וגם Eurythmics 1983.
        # בלי בחירה מפורשת נלקחה הראשונה והוחזרו עשרים גרסאות קאנטרי.
        hint = covers_module.famous_recording(cover_title)
        if hint:
            # הבורר מציג מלחינים, ומשתמש שמחפש "Umbrella" מזהה את השיר לפי המבצע.
            # בלי השורה הזאת נראה שהיצירה הנכונה חסרה, בעוד שהיא ראשונה ברשימה.
            st.caption(f"The well-known song by this name: "
                       f"**{hint['artist']}** — {hint['track']}"
                       + (f" ({hint['year']})" if hint.get("year") else ""))
        labels = {
            f"{c['title']}" + (f" — {c['disambiguation']}" if c["disambiguation"] else "")
            + (f" · writers: {c['writers']}" if c["writers"] else ""): c["id"]
            for c in work_candidates
        }
        picked = st.radio("Which work did you mean?", list(labels), index=0)
        chosen_work = labels[picked]

elif search_mode == MODE_ARTIST and cover_artist.strip():
    titles = _artist_preview_titles(cover_artist)
    if titles:
        st.caption(f"The {len(titles)} titles most associated with "
                   f"{cover_artist} — clicking one searches covers for that "
                   "song alone. 'Find covers' scans all of the top titles "
                   "at once.")
        _entry_grid([{"kind": "song", "artist": cover_artist, "track": title,
                      "rank": index + 1} for index, title in enumerate(titles)],
                    "artist_preview")
    else:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.caption("No titles found for this artist. You can still "
                       "press 'Find covers' for a direct cover search.")

run_search = _clicked_search or st.session_state.pop("auto_run", False)

# המכסה נגבית **רק כשחיפוש באמת עומד לרוץ**, ופעם אחת לחיפוש: היא מגנה על
# הקריאות היקרות לחנויות ולקטלוגים, לא על טעינת עמוד. כמו חסימת השמירה,
# היא פעילה רק כשהתחברות מוגדרת — אחרת פיתוח מקומי היה נגמר אחרי עשרה
# חיפושים בלי שיש למשתמש דרך להתחבר ולהמשיך.
_quota_blocked = False
if run_search and LOGIN_ENABLED and not accounts.spend(SUBJECT):
    run_search = False
    _quota_blocked = True

if _quota_blocked:
    st.error("You've used up your searches for now. They refill over time — "
             + ("or log in for your own allowance." if not SUBJECT.is_logged_in
                else "come back tomorrow."))


def _run_similar():
    """מבצע בקשת "עוד כמו זה" שנרשמה משורה, ומחליף את התוצאות המוצגות."""
    request = st.session_state.get("similar_of")
    if not request:
        return
    st.session_state["similar_of"] = None
    kind, track = request
    search_module.reset_errors()

    with st.spinner("Finding more like this..."):
        if kind == "covers":
            results, source = covers_module.more_covers_of(track)
            # אותו ניקוי שהחיפוש עצמו עשה, אחרת התווית אומרת "Yellow (Epic)"
            origin = track.get("origin_track") or search_module.clean_track_title(
                track["track"]) or track["track"]
            label = f"More covers of: {origin}"
        else:
            results, source = covers_module.more_like_style(track)
            label = f"Same style as: {track['artist']} — {track['track']}"
        results = apply_blacklist(results)

    st.session_state["candidates"] = results
    st.session_state["covers_source"] = f"{source} · {label}" if source else label
    st.session_state["original"] = None
    st.session_state["visible_count"] = PAGE_SIZE
    st.session_state["result_generation"] += 1
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("Nothing similar found.")


def _store_results(results, source, original=None):
    st.session_state["candidates"] = results
    st.session_state["covers_source"] = source
    st.session_state["original"] = original
    st.session_state["visible_count"] = PAGE_SIZE
    st.session_state["result_generation"] += 1
    st.session_state["last_query"] = cover_title or cover_artist


_run_similar()

if run_search:
    search_module.reset_errors()

if run_search and search_mode == MODE_ARTIST and not cover_artist.strip():
    st.warning("This search is by artist — fill in the artist field")

elif run_search and search_mode != MODE_ARTIST and not (
        cover_title.strip() or cover_artist.strip()):
    st.warning("Enter a song or artist name")

elif run_search and search_mode == MODE_ARTIST:
    with st.spinner("Finding the artist's songs and searching for covers..."):
        results, source_used, titles = covers_module.find_artist_covers(
            cover_artist, filters=filters, prefer_new=prefer_new,
            min_year=RECENCY_OPTIONS[recency])
        results = drop_seen(apply_blacklist(results),
                            st.session_state["seen_keys"] if fresh_only else None)
    _store_results(results, source_used)
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("No covers found for this artist. Check the spelling, "
                    "or try a specific song.")
    else:
        st.caption("Scanned: " + " · ".join(titles))

elif run_search and search_mode == MODE_SONG:
    with st.spinner("Searching the official catalogue and the stores..."):
        results, source_used, original = covers_module.find_all_covers(
            cover_title, cover_artist, filters=filters, prefer_new=prefer_new,
            min_year=RECENCY_OPTIONS[recency], work_id=chosen_work)
        results = drop_seen(apply_blacklist(results),
                            st.session_state["seen_keys"] if fresh_only else None)
    _store_results(results, source_used, original)
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info(f"No covers found for this song. Try '{MODE_FREE}'.")

elif run_search:  # MODE_FREE
    with st.spinner("Scanning iTunes and Deezer..."):
        exclude = st.session_state["seen_keys"] if fresh_only else frozenset()
        # בחיפוש החופשי השאילתה היא שם השיר אם הוזן, ואחרת שם האמן —
        # ורק במקרה השני נכון להתאים על שם האמן
        results = apply_blacklist(search_covers(
            cover_title or cover_artist, filters=filters, exclude_keys=exclude,
            origin_artist=cover_artist, prefer_new=prefer_new,
            match_artist=not cover_title,
            min_year=RECENCY_OPTIONS[recency]))
    _store_results(results, "store search")
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("No results. Try turning off 'Unheard only' or "
                    "widening the filters.")

original = st.session_state.get("original")
if original:
    st.caption(f"Reference version: **{original['artist']}** — {original['track']}"
               + (f" ({original['year']})" if original.get("year") else ""))

if st.session_state["covers_source"]:
    st.caption(f"Source: {st.session_state['covers_source']}")


# ---------- מסך פתיחה ----------

START_HERE_COUNT = 12
# מתוך כמה מהמוכרים ביותר להגריל. 150 הראשונים ברשימת Billboard הם
# שירים שכל אחד מזהה; מתחת לזה מתחילים שמות שדורשים היכרות.
START_HERE_POOL = 150


def _start_here():
    """מה שרואים לפני החיפוש הראשון.

    בלי זה המסך הוא שורת חיפוש שצפה בשמונים אחוז שחור — מה שנראה כמו
    טרמינל ולא כמו אפליקציית מוזיקה, וגם לא אומר למשתמש מה האפליקציה
    יודעת לעשות. ההנדאוף מציין את זה במפורש כמה שלא עוצב
    ("empty/onboarding states"), ולכן זה נבנה כאן בשפה של שאר המסכים.

    נקודות ההתחלה נלקחות מראש רשימת Billboard ("500 Best Pop Songs")
    ולא מבריכת ההגרלה כולה. הבריכה בנויה לגיוון והיא מכילה גם להיטי
    מצעד שאיש לא זוכר — הגרלה ממנה החזירה למסך הפתיחה שמות כמו
    "Mother-In-Law — Ernie K-Doe". מסך הפתיחה הוא חלון הראווה: כל שם בו
    חייב להיות מזוהה מיידית, אחרת הוא מרתיע במקום להזמין.
    לחיצה מריצה חיפוש מלא, בדיוק כמו לחיצה במצעדים.
    """
    # מוגרל פעם אחת לסשן ולא בכל ריצה: רשת שמתחלפת בכל לחיצה על כל
    # פקד אחר בדף היא רעש, לא הצעה
    if not st.session_state.get("start_here"):
        # הרשימה מסודרת מדירוג 500 ל-1, ולכן הסוף הוא הצד המוכר
        famous = list(classics_module.BILLBOARD_500_POP)[-START_HERE_POOL:]
        st.session_state["start_here"] = [
            {"kind": "song", "artist": entry["artist"], "track": entry["track"]}
            for entry in random.sample(famous, min(START_HERE_COUNT, len(famous)))
        ]

    st.html(
        "<div class='ts-resulthead'>"
        "<h2 class='ts-h2'>Find a cover worth cutting to</h2>"
        "<span class='ts-lede'>Every version is measured in your browser, "
        "so the loud ones rise to the top.</span>"
        "</div>")
    st.html("<div class='ts-railcap ts-startcap'>START WITH ONE OF THESE</div>")
    _entry_grid(st.session_state["start_here"], "start")


candidates = st.session_state["candidates"]

if not candidates and not run_search:
    _start_here()

if candidates:
    # סמן הדור עבור שומר הגלילה: כל עוד הוא לא השתנה, מקום הגלילה שווה
    # שחזור. חיפוש חדש מחליף אותו, והשומר מוותר על המקום הישן.
    st.markdown(
        f"<span data-result-generation='{st.session_state['result_generation']}' hidden></span>",
        unsafe_allow_html=True)
    display = list(candidates)
    if same_work_only:
        # רק כשיש בכלל אימות בתוצאות האלה. "קאברים לאמן", "עוד כמו זה"
        # והחיפוש החופשי אינם עוברים דרך הקטלוג, ולכן אין להם `work_verified`
        # — וסינון עליו רוקן את הרשימה עד "מוצגים 0 מתוך 0" (נבדק).
        if any("work_verified" in t for t in display):
            display = [t for t in display if t.get("work_verified")]
        else:
            st.caption(f"Catalogue verification only exists in the "
                       f"'{MODE_SONG}' search. These results came through a "
                       "different path, so they are shown as they are.")

    if sound_filter != ALL:
        # לפני `taste_profile`: הפרופיל נבנה מול הפול המוצג, ומדידה של
        # פול שכבר סונן היא מה שהופך את הלמידה לרלוונטית למה שרואים.
        _measurements = st.session_state.get("bigness", {})
        _before = len(display)
        display = [track for track in display
                   if tags_module.matches(_measurements.get(track["uid"]),
                                          sound_filter)]
        _unmeasured = sum(1 for track in display
                          if not audio.measured(_measurements.get(track["uid"])))
        if _unmeasured:
            # בלי המשפט הזה נראה שהמסנן לא עובד: השורות שטרם נמדדו
            # נשארות, והמשתמש רואה תוצאות שלכאורה לא תואמות למה שביקש.
            st.caption(f"{_unmeasured} of these have not been measured yet, "
                       f"so they are still shown. They will drop out of "
                       f"'{sound_filter}' once the browser measures them.")
        elif not display and _before:
            st.caption(f"Nothing measured here sounds like {sound_filter}.")

    # הפרופיל נבנה מול פול התוצאות המוצג — כך "אהבתי Soundtrack" נמדד מול
    # כמה Soundtrack יש כאן ממילא, ולא כספירה גולמית
    learned = taste_profile(display)

    display = ordered_display(display, sort_by, same_work_only, learned)

    # הכותרת אומרת **מה** נמצא ולא כמה שורות מצוירות: "63 covers of
    # Yellow" הוא המשפט שהמשתמש חיפש, ואילו "מוצגים 20 מתוך 63" הוא פרט
    # תפעולי שיורד לשורת ההסבר שלצידו.
    _subject = (st.session_state.get("last_query") or "").strip()
    _declared = sum(1 for t in display if t.get("trailer_indicator"))
    _shown = min(st.session_state["visible_count"], len(display))
    _lede = [f"{_declared} declare a trailer version"] if _declared else []
    _lede.append("measured in your browser")
    if _shown < len(display):
        _lede.insert(0, f"showing {_shown}")
    st.html(
        "<div class='ts-resulthead'>"
        f"<h2 class='ts-h2'>{len(display)} cover"
        f"{'' if len(display) == 1 else 's'}"
        + (f" of {html.escape(_subject)}" if _subject else "")
        + "</h2>"
        f"<span class='ts-lede'>{html.escape(' · '.join(_lede))}</span>"
        "</div>")

    # מתחת לכותרת ולא מעליה: זהו פקד תחזוקה של הסדר, והוא לא אמור להיות
    # הדבר הראשון שנקרא מעל רשימת התוצאות
    with st.container(key="resortrow"):
        resort_button(display, sort_by, learned)

    # שורת הקטגוריות: **מסננת, לא מפצלת.**
    #
    # פיצול למדפים נוסה ונמדד, ושבר שני דברים בבת אחת. הראשון: חברות
    # בקטגוריה "רגוע" נגזרת מהמדידה, שמגיעה מהדפדפן שניות אחרי שהתוצאות
    # כבר על המסך — ולכן שורות קפצו בין מדפים בדיוק כמו בתלונה שמקובעת
    # ב-`test_arriving_measurements_do_not_move_the_rows`. השני: מדף
    # קבוע הוציא את הקאבר החזק ביותר מראש הדף, בניגוד להבטחה של המסך
    # עצמו ("the loud ones rise to the top").
    #
    # כמסנן, הדירוג הגלובלי נשאר שלם — גרסאות הטריילר עדיין בראש דרך
    # `RANK_TRAILER` — והלחיצה רק מצמצמת את אותה רשימה מדורגת.
    _measurements = st.session_state.get("bigness", {})
    _counts = buckets.counts(display, _measurements)
    _present = [name for name in buckets.ORDER if _counts.get(name)]
    if len(_present) > 1:
        with st.container(key="kindrow"):
            _kind = st.pills(
                "Kind", [buckets.ALL, *_present], key="bucket_filter",
                format_func=lambda name: (f"All ({len(display)})" if name == buckets.ALL
                                          else f"{name} ({_counts[name]})"),
                label_visibility="collapsed")
        # None כשמבטלים את הבחירה בלחיצה חוזרת — אותה נפילה חזרה שכבר
        # נדרשה ב-`search_mode`, אחרת הלחיצה הזו מרוקנת את המסך
        if _kind and _kind != buckets.ALL:
            display = [track for track in display
                       if buckets.bucket_of(
                           track, _measurements.get(track["uid"])) == _kind]

    visible = display[: st.session_state["visible_count"]]

    measure_visible(visible)
    measure_via_server(visible)

    if youtube_module.available() and st.button(
            "Check trailer usage for the shown results", icon=":material/movie:"):
        progress = st.progress(0.0, text="Searching...")
        for index, track in enumerate(visible):
            progress.progress(index / max(len(visible), 1),
                              text=f"{index + 1}/{len(visible)}: {track['artist']}")
            st.session_state["evidence"][track["uid"]] = (
                youtube_module.search_trailer_evidence(track["artist"], track["track"]))
        progress.empty()
        st.rerun()

    for index, track in enumerate(visible):
        render_track(track, index, learned)

    if st.session_state["visible_count"] < len(display):
        if st.button(f"Load {PAGE_SIZE} more", icon=":material/expand_more:"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

