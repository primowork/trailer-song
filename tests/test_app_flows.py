"""זרימות ממשק שנשברו בעבר בשקט, ולכן נבדקות מקצה לקצה.

שתי תקלות אמיתיות שנתפסו כאן: Streamlit אוסר על שינוי `session_state` של widget
אחרי שהוא נוצר, ולכן כפתור שמצויר מתחת לשדה לא יכול לכתוב אליו ישירות — גם
כפתורי ההשלמה וגם רשימת האמנים נפלו על זה. מפתח widget כפול מפיל את העמוד כולו.
"""
import os

import pytest

from streamlit.testing.v1 import AppTest

import artists
import covers
import storage
import search as search_module
import suggest as suggest_module
# מדידה אחת לכל תגית, שנבנתה מהטווחים המתועדים ב-`audio.py`. מיובאת ולא
# משוכפלת: מספרים גולמיים שנכתבים כאן שוב היו מפסיקים לתאר את התגית
# ברגע שהכיול הבא ישנה טווח.
from test_tags import SATISFYING as _SATISFYING

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def tags_measurement(name):
    """מדידה גולמית שמדליקה את התגית הזו ואותה בלבד מבין ההפכים שלה."""
    return dict(_SATISFYING[name])


def track(artist, title, uid, **extra):
    return {"source": "iTunes", "uid": f"itunes-{uid}", "artist": artist,
            "track": title, "album": "", "duration_sec": 200,
            "preview_url": "http://p", "artwork": "", "genre": "",
            "release_date": "", "year": "2020", "score": 50, **extra}


class _UserWithoutAuth:
    """מה ש-Streamlit נותן כשאין בלוק `[auth]`: כל גישה לתכונה זורקת."""

    def __getattr__(self, name):
        raise AttributeError(f'st.user has no attribute "{name}".')


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """מבודד כל טסט מהדיסק המשותף — בלי זה טסטים חולקים קאש/רשימה שחורה בין ריצות.

    ומבודד גם מ**הגדרת ההתחברות של המכונה**. `accounts.login_available()`
    מסתכל על `st.user`, שנשען על `.streamlit/secrets.toml` — כלומר מפתח
    שיוצר קובץ כזה כדי לבדוק התחברות מקומית היה מדליק את חומת השמירה
    בכל הטסטים בבת אחת, והם היו נופלים מסיבה סביבתית. ברירת המחדל כאן
    היא "אין auth", ומי שבודק את מסלול ההתחברות מחליף את זה במפורש.
    """
    import accounts
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(accounts.st, "user", _UserWithoutAuth())


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


def test_the_page_renders(app):
    assert not app.exception


# ---------- מסך הפתיחה ----------

def _start_buttons(app):
    return [b for b in app.button if (b.key or "").startswith("start_")]


def test_the_first_screen_is_not_an_empty_page(app):
    """לפני החיפוש הראשון היה כאן שחור ריק עם שורת חיפוש שצפה בתוכו.

    זה נראה כמו טרמינל, וגם לא אמר למשתמש מה האפליקציה יודעת לעשות.
    אף טסט אחר לא נוגע במצב הריק, ולכן בלי הטסט הזה החזרה של הריק
    הייתה עוברת בשקט.
    """
    assert not app.exception
    assert not app.session_state["candidates"], "הטסט הזה בודק את המצב הריק"
    assert _start_buttons(app), "אין נקודות התחלה במסך הריק"


def test_the_start_screen_offers_songs_people_recognise(app):
    """נקודות ההתחלה הן חלון הראווה, ולכן הן מראש רשימת Billboard ולא
    מבריכת ההגרלה — שמכילה גם להיטי מצעד שאיש לא זוכר."""
    import classics

    import app as app_module

    # הגבול נקרא מהקוד ולא מוקלד כאן: מספר שמוקלד פעמיים במקומות רחוקים
    # מפסיק להיות אותו מספר בדיוק כשמשנים אותו
    famous = {(e["artist"], e["track"])
              for e in list(classics.BILLBOARD_500_POP)[-app_module.START_HERE_POOL:]}
    offered = {(e["artist"], e["track"])
               for e in app.session_state["start_here"]}
    assert offered, "לא הוגרלו נקודות התחלה"
    assert offered <= famous, "נקודת התחלה שאינה מראש הרשימה המוכרת"


def test_the_start_screen_makes_way_for_results(app):
    """ברגע שיש תוצאות, המסך הריק אינו רלוונטי ואסור לו להישאר מעליהן."""
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "s1")]
    app.run()

    assert not app.exception
    assert not _start_buttons(app), "נקודות ההתחלה נשארו מעל התוצאות"


def test_the_start_picks_do_not_reshuffle_on_every_interaction(app):
    """רשת שמתחלפת בכל לחיצה על כל פקד אחר בדף היא רעש, לא הצעה."""
    before = list(app.session_state["start_here"])
    app.text_input(key="cover_title").set_value("Yellow").run()

    assert app.session_state["start_here"] == before


def _page_css(app) -> str:
    return " ".join(m.value for m in app.markdown if "<style>" in (m.value or ""))


def _rendered(app) -> str:
    """כל מה שמצויר על המסך — markdown וגם `st.html`.

    שם האמן ומד העוצמה עברו ל-`st.html` (הם כותרת השורה וגרפיקה, לא
    פסקאות), ולכן בדיקה שמסתכלת רק על `app.markdown` מפספסת בדיוק את
    מה שהמשתמש רואה קודם.
    """
    return " ".join(
        [str(m.value) for m in app.markdown if m.value]
        + [str(e.proto) for e in app.get("html")])


def _html_bodies(app) -> str:
    """ה-HTML הגולמי של `st.html`, בלי לעבור דרך ה-proto.

    `_rendered` ממיר את ה-proto למחרוזת, וה-repr שלו **מברח תווים
    שאינם ASCII**: מקף em (—) מופיע שם כ-`\342\200\224`. בדיקה של
    טקסט שמכיל תו כזה מול `_rendered` נכשלת גם כשהעמוד תקין לגמרי.
    """
    return " ".join(str(getattr(e, "body", "")) for e in app.get("html"))


def _nav(app, item):
    """בוחר פריט ניווט ב-rail ומריץ מחדש.

    מאז המעבר ל-rail, הפלייליסט, ההגדרות ואינדקס המצעדים אינם מרונדרים
    יחד — כל אחד מהם הוא מסך. טסט שנוגע באחד מהם חייב לבחור אותו קודם,
    בדיוק כמו המשתמש.
    """
    app.session_state["rail_nav"] = item
    return app.run()


def test_nothing_forces_a_direction_on_the_page(app):
    """הממשק אנגלי ו-LTR, ולכן אסור שיישאר כלל כיווניות כלשהו.

    זה לא ניקיון: `direction: rtl` על השורש הפך בעבר את ה-`translateX`
    השלילי שבו Streamlit מקפל את הסרגל בטלפון — הסרגל נשאר על המסך, נמעך
    לכ-50px, וחפף לתוכן. כלל RTL ששרד את המעבר לאנגלית היה מחזיר בדיוק
    את הבאג הזה, בלי שאף אחד יחפש אותו שם.
    """
    assert "direction: rtl" not in _page_css(app)


def test_the_content_column_is_capped_so_it_does_not_stretch(app):
    """ב-layout="wide" הטופס נמתח על פני 1400px ומפזר את העין."""
    assert "max-width: 1180px" in _page_css(app)


def test_classics_is_the_default_index_source_and_needs_no_network(app):
    # אין כאן שום monkeypatch לרשת — קלאסיקות היא רשימה סטטית
    _nav(app, "Charts")
    _nav(app, "Charts")
    assert app.radio(key="index_source").value.startswith("Classics")
    assert any((b.key or "").startswith("classic_") for b in app.button)


def test_classics_song_click_runs_a_focused_song_search(app, monkeypatch):
    import classics
    # הקטגוריה הראשונה היא ברירת המחדל של ה-selectbox
    first = classics.CATEGORIES[next(iter(classics.CATEGORIES))][0]
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track(first["artist"], f"{title} (Cover)", "c1")], "src", None))

    _nav(app, "Charts")
    classics_button = [b for b in app.button if (b.key or "").startswith("classic_")][0]
    classics_button.click().run()

    assert not app.exception
    assert app.session_state["search_mode"] == "Covers of a song"
    assert app.session_state["cover_title"] == first["track"]
    assert app.session_state["cover_artist"] == first["artist"]
    assert app.session_state["candidates"]


def test_picking_a_song_leaves_the_chart_index_for_the_results(app, monkeypatch):
    """הבחירה במצעד היא בקשה לראות תוצאות, ולכן היא מחזירה ל-Discover.

    קודם האינדקס היה אקספנדר שנסגר בעזרת מפתח נגזר-מונה (העברת
    `expanded=False` כשהוא כבר False אינה סוגרת דבר). כמסך נפרד אין צורך
    בפטנט — אבל התוצאה למשתמש חייבת להישאר זהה: אחרי לחיצה על שיר הוא
    רואה את התוצאות ולא רשת של 120 כפתורים.
    """
    import classics
    first = classics.CATEGORIES[next(iter(classics.CATEGORIES))][0]
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track(first["artist"], f"{title} (Cover)", "c1")], "src", None))

    _nav(app, "Charts")
    [b for b in app.button if (b.key or "").startswith("classic_")][0].click().run()

    assert not app.exception
    assert app.session_state["rail_nav"] == "Discover"


def test_picking_an_artist_also_leaves_the_index(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    _nav(app, "Charts")
    _nav(app, "Charts")
    source = app.radio(key="index_source")
    source.set_value(source.options[1]).run()

    app.button(key="goat_0").click().run()

    assert not app.exception
    assert app.session_state["rail_nav"] == "Discover"


# ---------- הגרלת שיר מוכר ----------

def _dice(app):
    # לפי key ולא לפי תווית: הכפתור הוא אייקון בתוך שורת החיפוש
    return app.button(key="btn_dice")


def test_the_dice_fills_both_fields_but_does_not_search(app, monkeypatch):
    """ההגרלה והחיפוש מופרדים, לבקשת המשתמש.

    לחיצה חוזרת על הכפתור מגלגלת שירים עד שאחד מוצא חן; החיפוש — שהוא
    היקר, קריאות רשת לקטלוג ולחנויות — רץ רק ב-"Find covers". קודם כל
    גלגול יצא לרשת מיד, כלומר עשרה גלגולים היו עשרה חיפושים מלאים שאיש
    לא ביקש.
    """
    import classics
    called = {"n": 0}

    def _counted(title, artist="", **k):
        called["n"] += 1
        return [track("Someone", f"{title} (Cover)", "d1")], "src", None

    monkeypatch.setattr(covers, "find_all_covers", _counted)

    _dice(app).click().run()

    assert not app.exception
    rolled = (app.session_state["cover_artist"], app.session_state["cover_title"])
    assert all(rolled)
    assert rolled in {(e["artist"], e["track"]) for e in classics.famous_pool()}
    assert app.session_state["search_mode"] == "Covers of a song"
    assert called["n"] == 0, "ההגרלה יצאה לרשת בלי שביקשו חיפוש"
    assert not app.session_state["candidates"]


def test_no_completion_block_goes_to_the_catalogue(app, monkeypatch):
    """שורת ההשלמות הוסרה כולה, ואיתה הקריאה שהיא הריצה.

    היא רצה בכל ריצת סקריפט ופנתה לרשת בכל שינוי בטקסט — בטלפון היא
    דחפה את התוצאות מתחת לקפל, וזו אותה קריאה שגרמה לקובייה להיראות
    כאילו היא מחפשת מיד. ההשתקה שנוספה קודם רק סתמה אותה אחרי גלגול;
    כאן הסיבה עצמה איננה, ולכן הבדיקה היא שגם הקלדה חופשית לא פונה
    לשום מקום.
    """
    called = {"suggest": 0, "covers": 0}

    def _suggest(query, limit=6):
        called["suggest"] += 1
        return []

    def _covers(title, artist="", **k):
        called["covers"] += 1
        return [], "src", None

    monkeypatch.setattr(suggest_module, "suggest", _suggest)
    monkeypatch.setattr(covers, "find_all_covers", _covers)

    _dice(app).click().run()
    assert not app.exception
    assert app.session_state["cover_title"], "הקובייה לא מילאה את השדה"

    app.session_state["cover_title"] = "bitter sweet symphany"
    app.run()

    assert not app.exception
    assert called == {"suggest": 0, "covers": 0}


def test_the_search_button_runs_what_the_dice_rolled(app, monkeypatch):
    """הצד השני של אותה הפרדה: מה שהוגרל אכן נחפש כשלוחצים."""
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track("Someone", f"{title} (Cover)", "d1")], "src", None))

    _dice(app).click().run()
    rolled = app.session_state["cover_title"]
    app.button(key="btn_search").click().run()

    assert not app.exception
    assert app.session_state["candidates"]
    assert app.session_state["cover_title"] == rolled


def test_two_rolls_in_a_row_are_not_the_same_song(app, monkeypatch):
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: ([], "src", None))

    _dice(app).click().run()
    first = app.session_state["cover_title"]
    _dice(app).click().run()

    assert not app.exception
    assert app.session_state["cover_title"] != first
    assert len(app.session_state["recent_rolls"]) == 2


def test_the_roll_history_stays_bounded(app, monkeypatch):
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: ([], "src", None))

    for _ in range(8):
        _dice(app).click().run()

    assert not app.exception
    assert len(app.session_state["recent_rolls"]) == 5


def test_greatest_artist_click_shows_a_preview_before_searching(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=12, filters=None, prefer_new=False, min_year=0:
                            ([track("Epic", f"{title} (Epic)", "e1")], "src"))

    # האינדקס נפתח על המצעד החי; רשימת בילבורד היא המקור השני
    _nav(app, "Charts")
    source = app.radio(key="index_source")
    source.set_value(source.options[1]).run()
    app.button(key="goat_0").click().run()

    assert not app.exception
    assert app.session_state["cover_artist"] == artists.GREATEST_ARTISTS[0]
    assert app.session_state["search_mode"] == "Covers of an artist"
    # לא הורץ חיפוש קאברים יקר מיד — קודם מוצגת תצוגה מקדימה זולה
    assert app.session_state["candidates"] == []
    assert any("Yesterday" in b.label for b in app.button
              if (b.key or "").startswith("artist_preview_"))

    # "חפש" מריץ את החיפוש המלא לפי האמן, בדיוק כמו היום
    search_button = [b for b in app.button if b.key == "btn_search"][0]
    search_button.click().run()

    assert not app.exception
    assert app.session_state["candidates"]
    assert app.session_state["candidates"][0]["origin_track"] == "Yesterday"


def test_artist_preview_song_click_runs_a_focused_song_search(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track("Beatles", f"{title} (Cover)", "c1")], "src", None))

    _nav(app, "Charts")
    source = app.radio(key="index_source")
    source.set_value(source.options[1]).run()
    app.button(key="goat_0").click().run()

    preview_button = [b for b in app.button
                     if (b.key or "").startswith("artist_preview_")][0]
    preview_button.click().run()

    assert not app.exception
    assert app.session_state["search_mode"] == "Covers of a song"
    assert app.session_state["cover_title"] == "Yesterday"
    assert app.session_state["candidates"]
    assert app.session_state["candidates"][0]["uid"] == "itunes-c1"


def test_sounds_like_filters_on_the_measurement_not_the_title(app):
    """המסנן היחיד שפועל על התוצאות המוצגות ולא בחנות.

    לחנות אין מושג איך טראק נשמע, ולכן "Sounds like" עובד על המדידה
    שכבר נשמרה. שתי השורות כאן נבדלות רק במספרים: הכותרות שלהן זהות
    כמעט לגמרי, וזה בדיוק העניין.
    """
    import tags

    loud = tags_measurement(tags.ACTION)
    quiet = tags_measurement(tags.INTIMATE)
    app.session_state["candidates"] = [track("A", "Yellow (One)", "a1"),
                                       track("B", "Yellow (Two)", "b1")]
    app.session_state["bigness"] = {"itunes-a1": loud, "itunes-b1": quiet}
    app.session_state["filter_sound"] = tags.ACTION
    app.run()

    assert not app.exception
    shown = " ".join(str(e.proto) for e in app.get("html"))
    assert "Yellow (One)" in shown
    assert "Yellow (Two)" not in shown, "המסנן לא הוריד את השורה השקטה"


def test_a_row_that_was_not_measured_survives_the_sound_filter(app):
    """אחרת המסנן היה מרוקן את הרשימה בכל חיפוש חדש, לפני שהדפדפן הספיק
    למדוד ולו שורה אחת."""
    import tags

    app.session_state["candidates"] = [track("A", "Yellow (One)", "a1")]
    app.session_state["bigness"] = {}
    app.session_state["filter_sound"] = tags.ACTION
    app.run()

    assert not app.exception
    shown = " ".join(str(e.proto) for e in app.get("html"))
    assert "Yellow (One)" in shown


def test_a_measured_row_shows_a_measured_tag_that_is_not_amber(app):
    """תג נמדד אחד בשורה, ובאפור: מערכת העיצוב שומרת את הענבר לפעולה
    הראשית ולדרגת ה"ענק", ואקסנט על כל שורה מפסיק לסמן משהו."""
    import tags

    app.session_state["candidates"] = [track("A", "Yellow (One)", "a1")]
    app.session_state["bigness"] = {"itunes-a1": tags_measurement(tags.ACTION)}
    app.run()

    assert not app.exception
    shown = " ".join(str(e.proto) for e in app.get("html"))
    assert "ts-tag-heard" in shown, "אין תג נמדד על שורה שנמדדה"
    assert tags.ACTION.upper() in shown


def test_more_like_this_replaces_the_list(app, monkeypatch):
    app.session_state["candidates"] = [track("Epic Covers", "Yellow (Epic)", "e1")]
    app.run()

    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=40, filters=None, prefer_new=False, min_year=0:
                            ([track("Other", f"{title} (Cinematic)", "o1")], "src"))
    monkeypatch.setattr(covers, "find_covers", lambda *a, **k: ([], "", None))
    app.button(key="more_covers_itunes-e1").click().run()

    assert not app.exception
    assert [t["uid"] for t in app.session_state["candidates"]] == ["itunes-o1"]


def test_measured_row_shows_the_score_as_a_meter_and_keeps_the_numbers(app):
    """העוצמה היא מד שקוראים לרוחב, והמספרים הגולמיים ירדו ל-⋯ ולא נמחקו.

    המד החליף תג: תג נקרא שורה-שורה, בעוד שרצועה באורך קבוע מאפשרת
    להשוות את כל התוצאות במבט אחד. מה שנבדק כאן הוא ששלושת החלקים
    קיימים — הרצועה, המילוי בצבע המדרגה, והמספר עצמו.
    """
    app.session_state["candidates"] = [track("Epic Covers", "Yellow (Epic)", "e1")]
    app.session_state["bigness"] = {"itunes-e1": {"loudness": 0.30, "low_end": 3.0,
                                                 "onset_rate": 4.0, "dynamic_span": 6.0}}
    app.run()

    assert not app.exception
    html = " ".join(str(e.proto) for e in app.get("html"))
    assert "ts-meterfill" in html, "אין מד עוצמה על השורה"
    # ענבר שמור למדרגת "גדול", וזו בדיוק מדידה גדולה
    assert "#FFB020" in html

    # המספרים הגולמיים כבר לא מוצגים למשתמש (ראו
    # `test_the_overflow_menu_speaks_in_words_not_in_debug_output`), אבל
    # הפונקציה שמייצרת אותם חייבת להישאר עובדת — היא כלי הכיול.
    import audio as audio_module
    assert "loudness" in audio_module.describe(
        app.session_state["bigness"]["itunes-e1"])


def test_chart_song_click_fills_both_fields_and_runs_the_epic_search(monkeypatch):
    imported = {"hot-100": {"title": "Hot 100", "slug": "hot-100", "kind": "songs",
                            "entries": [{"rank": 1, "artist": "Rihanna", "track": "Umbrella"}]}}
    # המצעד המיובא חייב להיות קיים כבר ברינדור הראשון, אחרת הוא אינו אחת
    # מאפשרויות מקור האינדקס שאפשר לבחור
    monkeypatch.setattr(storage, "load_charts", lambda: imported)
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=60, filters=None, prefer_new=False, min_year=0: (
                            [track("Epic", f"{title} (Epic Trailer Version)", "e1")], "src"))
    monkeypatch.setattr(covers, "find_covers", lambda *a, **k: ([], "", None))

    app = AppTest.from_file(APP, default_timeout=120).run()
    _nav(app, "Charts")
    source = app.radio(key="index_source")
    source.set_value(source.options[-1]).run()
    app.button(key="imp_hot-100_0").click().run()

    assert not app.exception
    assert app.session_state["cover_title"] == "Umbrella"
    assert app.session_state["cover_artist"] == "Rihanna"
    assert app.session_state["search_mode"] == "Covers of a song"
    assert app.session_state["candidates"]


def test_search_mode_has_two_options(app):
    """'Free search' הוסר: השלמת השם החיה בשדה עצמו כבר עונה על אותה
    כוונה מהר יותר, ואף אחד לא היה במצב הזה בפועל."""
    modes = app.get("button_group")[0]
    assert modes.options == ["Covers of a song", "Covers of an artist"]


def test_an_artist_alone_in_song_mode_gets_a_helpful_warning(app, monkeypatch):
    """נמדד: 'Daft Punk' לבד ב-Covers of a song חיפש שיר ריק וחזר עם
    'No covers found', בלי לרמוז שהפתרון הוא למלא שיר או לעבור מצב."""
    called = {}
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda *a, **k: called.setdefault("hit", True))
    app.text_input(key="cover_artist").set_value("Daft Punk").run()
    [b for b in app.button if b.key == "btn_search"][0].click().run()

    assert not app.exception
    assert not called.get("hit")
    assert any("switch to 'Covers of an artist'" in (w.value or "") for w in app.warning)


def test_song_mode_dispatches_to_find_all_covers(app, monkeypatch):
    called = {}
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda *a, **k: (called.setdefault("hit", True) and
                                        [track("X", "Y", "y1")], "src", None))
    app.text_input(key="cover_title").set_value("Yellow").run()
    search_button = [b for b in app.button if b.key == "btn_search"][0]
    search_button.click().run()

    assert not app.exception
    assert called.get("hit")
    assert app.session_state["candidates"][0]["uid"] == "itunes-y1"


def test_the_loading_skeleton_is_wired_up_but_does_not_linger(app, monkeypatch):
    """שלד הטעינה מוצג רק בזמן שהחיפוש רץ. `AppTest` מריץ סקריפט עד
    הסוף בלי לעצור באמצע, ולכן אי אפשר לתפוס כאן את הרגע הביניים עצמו —
    אבל אפשר לוודא שה-CSS שלו קיים בעמוד, ושהוא לא נשאר על המסך אחרי
    שהתוצאות האמיתיות כבר שם."""
    assert ".ts-skel-row" in _page_css(app)

    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: ([track("X", "Y", "y1")], "src", None))
    app.text_input(key="cover_title").set_value("Yellow").run()
    [b for b in app.button if b.key == "btn_search"][0].click().run()

    assert not app.exception
    assert "ts-skel-row" not in _html_bodies(app)


def test_artist_mode_dispatches_to_find_artist_covers(app, monkeypatch):
    called = {}
    monkeypatch.setattr(covers, "find_artist_covers",
                        lambda *a, **k: (called.setdefault("hit", True) and
                                        [track("X", "Y", "y2")], "src", ["Y"]))
    modes = app.get("button_group")[0]
    modes.set_value("Covers of an artist").run()
    app.text_input(key="cover_artist").set_value("Coldplay").run()
    search_button = [b for b in app.button if b.key == "btn_search"][0]
    search_button.click().run()

    assert not app.exception
    assert called.get("hit")
    assert app.session_state["candidates"][0]["uid"] == "itunes-y2"


def test_filters_thread_through_to_song_mode(app, monkeypatch):
    """לפני האיחוד רק החיפוש החופשי כיבד את הפילטרים; עכשיו כולם."""
    seen = {}

    def fake(title, artist="", filters=None, prefer_new=False, min_year=0, work_id="", limit=80):
        seen["filters"] = filters
        return [], "", None

    monkeypatch.setattr(covers, "find_all_covers", fake)
    app.text_input(key="cover_title").set_value("Yellow").run()
    search_button = [b for b in app.button if b.key == "btn_search"][0]
    search_button.click().run()

    assert not app.exception
    assert seen["filters"] is not None


# ---------- ❤️ פלייליסט וטעם נלמד ----------

def test_heart_saves_to_the_playlist_and_persists(app):
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    app.button(key="btn_favorite_itunes-e1").click().run()

    assert not app.exception
    assert len(app.session_state["favorites"]) == 1
    # נשמר לדיסק, לא רק ל-session (ה-fixture מפנה את DATA_DIR ל-tmp_path)
    assert storage.load_favorites()
    saved = list(app.session_state["favorites"].values())[0]
    assert saved["artist"] == "2WEI"
    assert saved["track"] == "Zombie (Epic)"


def test_a_result_is_one_card_and_not_a_row_of_eight_columns(app):
    """Streamlit לא מכווץ עמודות בטלפון אלא עורם אותן לרוחב מלא.

    שורת התוצאה הייתה בנויה משמונה עמודות, ולכן כל תוצאה הפכה בטלפון
    לשמונה בלוקים נפרדים — עשרים תוצאות היו 160 בלוקים. הבדיקה סופרת את
    העמודות שכל תוצאה מוסיפה בפועל, ולא את מראה העמוד.
    """
    app.session_state["candidates"] = [track("2WEI", "One", "u1")]
    app.run()
    one = len(app.columns)

    app.session_state["candidates"] = [track("2WEI", f"T{i}", f"u{i}") for i in range(4)]
    app.run()
    four = len(app.columns)

    assert not app.exception
    assert (four - one) / 3 <= 2, "תוצאה בודדת פורשת יותר משתי עמודות"


def test_heart_toggles_off(app):
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    app.button(key="btn_favorite_itunes-e1").click().run()
    assert len(app.session_state["favorites"]) == 1
    app.button(key="btn_favorite_itunes-e1").click().run()

    assert not app.exception
    assert app.session_state["favorites"] == {}


# ---------- הפלייליסט: קיבוץ לפי שיר מקור ----------

def _save(app, artist, title, uid, searched="Bitter Sweet Symphony",
          origin_artist="The Verve", **extra):
    """שומר גרסה לפלייליסט, ומשאיר את ה-rail על Loved.

    הלייק עצמו נלחץ בתוצאות (מסך Discover), והפלייליסט נצפה במסך Loved —
    שני מסכים, כמו אצל המשתמש. לכן ההחלפה בשני הכיוונים כאן, ולא בכל
    טסט בנפרד.
    """
    app.session_state["rail_nav"] = "Discover"
    app.session_state["cover_title"] = searched
    app.session_state["cover_artist"] = origin_artist
    app.session_state["candidates"] = [track(artist, title, uid, **extra)]
    app.run()
    app.button(key=f"btn_favorite_itunes-{uid}").click().run()
    _nav(app, "Loved")


def test_saving_a_cover_records_the_song_it_covers(app):
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")

    assert not app.exception
    saved = list(app.session_state["favorites"].values())[0]
    # `clean_track_title` מסירה את תגית הגרסה ומשאירה את שם השיר
    # מה שהמשתמש חיפש, ולא ניחוש מהכותרת של הגרסה
    assert saved["origin"]["track"] == "Bitter Sweet Symphony"
    assert saved["origin"]["artist"] == "The Verve"


def test_two_covers_of_the_same_song_share_a_group(app):
    import app as app_module

    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")
    _save(app, "Hidden Citizens", "Bittersweet Symphony (Cover)", "b")
    _save(app, "Tommee Profitt", "In the End (Dark Cover)", "c", searched="In the End")

    assert not app.exception
    keys = [app_module.origin_key(e) for e in app.session_state["favorites"].values()]
    assert len(set(keys)) == 2, "שתי גרסאות של אותו שיר לא נפלו לאותה קבוצה"


def test_an_entry_saved_before_the_field_existed_still_groups(app):
    """הנפילה לאחור: פלייליסט קיים מתקבץ בלי לגעת ב-favorites.json."""
    import app as app_module

    legacy = {"artist": "2WEI", "track": "Yellow (Epic Trailer Version)",
              "features": None, "added_at": 1.0}
    fresh = {"artist": "Hidden Citizens", "track": "Yellow (Cover)",
             "origin": {"track": "Yellow", "artist": ""},
             "features": None, "added_at": 2.0}

    assert app_module.origin_key(legacy) == app_module.origin_key(fresh)


def test_a_saved_version_offers_its_artist_and_title_for_copying(app):
    """מה שמודבק לתוכנת העריכה או לחיפוש הוא "אמן — שיר", ובפלייליסט
    שם השיר אפילו לא מופיע בשורה (הוא כותרת הקבוצה), ולכן אי אפשר
    פשוט לסמן אותו עם העכבר."""
    _save(app, "Caroline Pennell", "Yellow", "cp")

    assert not app.exception
    shown = _html_bodies(app)
    assert "ts-copy" in shown, "אין כפתור העתקה בשורה"
    assert "data-copy='Caroline Pennell — Yellow'" in shown


def test_the_copy_text_survives_a_quote_in_the_name(app):
    """שם עם גרש או מרכאות סוגר את המאפיין ושובר את ה-HTML של השורה."""
    _save(app, 'Ricardo "RikRok" Ducent', "It Wasn't Me", "rr")

    assert not app.exception
    shown = _html_bodies(app)
    assert "&quot;RikRok&quot;" in shown
    assert "data-copy='Ricardo &quot;RikRok&quot; Ducent — It Wasn&#x27;t Me'" in shown


def test_the_sidebar_group_header_is_the_song_and_the_artist_only(app):
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")
    _save(app, "Hidden Citizens", "Bittersweet Symphony (Cover)", "b")

    assert not app.exception
    headers = " ".join(str(b.proto) for b in app.get("expander"))
    assert "Bitter Sweet Symphony" in headers and "The Verve" in headers
    # בלי מונה: הגרסאות נספרות במבט אחד ברגע שפותחים את הקבוצה
    assert "גרסאות" not in headers and "גרסה" not in headers


def test_a_work_chosen_for_one_song_is_not_used_for_the_next_search(monkeypatch):
    """בחירת היצירה של "Sweet Dreams" שרדה הקלדה של "Yellow", ו-`work_id`
    שלה נשלח לחיפוש — `find_covers` מדלגת אז על זיהוי היצירה ומחזירה גרסאות
    של השיר הלא נכון, בלי שום סימן למשתמש."""
    import covers as covers_module

    calls = []
    monkeypatch.setattr(covers_module, "find_all_covers",
                        lambda title, artist="", **k: (
                            calls.append((title, k.get("work_id"))) or ([], "מדומה", None)))
    monkeypatch.setattr(covers_module, "musicbrainz_work_candidates",
                        lambda title, artist="", client=None: [
                            {"id": "work-country", "title": "Sweet Dreams",
                             "disambiguation": "1955", "writers": ""},
                            {"id": "work-eurythmics", "title": "Sweet Dreams",
                             "disambiguation": "1983", "writers": ""}])

    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.text_input(key="cover_title").set_value("Sweet Dreams").run()
    [b for b in at.button if "Which songs have this name" in b.label][0].click().run()
    chooser = [r for r in at.radio if "Which work did you mean" in r.label]
    assert chooser, "בורר היצירה לא הופיע"
    chooser[0].set_value(list(chooser[0].options)[1]).run()

    at.text_input(key="cover_title").set_value("Yellow").run()
    [b for b in at.button if b.key == "btn_search"][0].click().run()

    assert not at.exception
    assert calls == [("Yellow", "")], f"נשלח work_id של שיר אחר: {calls}"
    assert not [r for r in at.radio if "איזו יצירה" in r.label], \
        "בורר היצירה של השיר הקודם עדיין על המסך"


def test_only_unseen_applies_to_the_cover_search_too(app):
    """הצ'קבוק פעל רק בחיפוש החופשי, ולא במצב שבו המשתמש נמצא רוב הזמן."""
    import app as app_module

    seen = {search_module.track_key("2WEI", "Zombie")}
    tracks = [track("2WEI", "Zombie", "a"), track("Hidden Citizens", "Alive", "b")]

    assert [t["uid"] for t in app_module.drop_seen(tracks, None)] == \
        ["itunes-a", "itunes-b"], "בלי הסימון שום דבר לא יורד"
    assert [t["uid"] for t in app_module.drop_seen(tracks, seen)] == ["itunes-b"]


class _AnonymousVisitor:
    """auth מוגדר, אבל אף אחד לא מחובר."""
    is_logged_in = False


class _SignedInVisitor:
    is_logged_in = True
    email = "owner@example.com"


def test_the_page_renders_with_sign_in_enabled(app, monkeypatch):
    """מסלול ההתחברות **כולו** לא היה מכוסה, ולכן באג בו יכול היה
    להתגלות רק בפרודקשן ברגע שמגדירים auth — וזה בדיוק מה שקרה:
    `_remember_anon` ביקש iframe בגובה 0, ש-Streamlit 1.62 פוסל, כך
    שכל טעינת עמוד הייתה קורסת ברגע שההתחברות נדלקת. הטסט הזה מריץ את
    העמוד עם auth דלוק כדי שזה לא יוכל לקרות שוב בשקט.
    """
    import accounts
    monkeypatch.setattr(accounts.st, "user", _AnonymousVisitor())
    app.run()

    assert not app.exception
    assert [b for b in app.button if b.key == "btn_login"], "אין כפתור התחברות"


def test_saving_needs_an_account_once_sign_in_is_enabled(app, monkeypatch):
    """החומה עצמה: אנונימי יכול לחפש ולהאזין, אבל לא לשמור."""
    import accounts
    monkeypatch.setattr(accounts.st, "user", _AnonymousVisitor())
    app.session_state["candidates"] = [track("Some Band", "Yellow", "y1")]
    app.run()

    app.button(key="btn_favorite_itunes-y1").click().run()

    assert not app.exception
    assert app.session_state["favorites"] == {}, "אנונימי הצליח לשמור"


def test_a_signed_in_visitor_can_save_and_sees_their_account(app, monkeypatch):
    """הצד השני של אותה חומה."""
    import accounts
    monkeypatch.setattr(accounts.st, "user", _SignedInVisitor())
    app.session_state["candidates"] = [track("Some Band", "Yellow", "y1")]
    app.run()

    assert not app.exception
    assert [b for b in app.button if b.key == "btn_logout"], "אין כפתור התנתקות"

    app.button(key="btn_favorite_itunes-y1").click().run()

    assert not app.exception
    assert app.session_state["favorites"], "משתמש מחובר לא הצליח לשמור"


def test_a_category_row_narrows_the_results(app):
    """שורת הקטגוריות מסננת את הרשימה המדורגת, ולא מפצלת אותה למדפים."""
    import buckets

    app.session_state["candidates"] = [
        track("Band A", "Yellow (Epic Trailer Version)", "a"),
        track("Band B", "Yellow (Metal Cover)", "b"),
        track("Band C", "Yellow (A Cappella)", "c"),
    ]
    app.run()

    assert not app.exception
    # בלי בחירה — הכל מוצג
    shown = _rendered(app)
    for artist in ("Band A", "Band B", "Band C"):
        assert artist in shown

    app.pills[0].set_value(buckets.ROCK).run()

    assert not app.exception
    shown = _rendered(app)
    assert "Band B" in shown
    assert "Band A" not in shown and "Band C" not in shown


def test_a_cached_measurement_reaches_the_category_row_on_the_same_run(app):
    """התלונה: הכפתור "עדין" לא הופיע אף פעם.

    חלק מזה היה סדר הקריאות ולא הספים: ההידרציה מהקאש רצה בתוך לולאת
    השורות, כלומר **אחרי** ששורת הקטגוריות כבר חושבה — ולכן הקטגוריות
    שנשענות על מדידה חושבו על סשן ריק, בזמן שהמד לצד השורה כבר הראה את
    אותה מדידה בדיוק.
    """
    import audio
    import buckets
    import tags

    quiet = tags_measurement(tags.INTIMATE)
    assert audio.bigness(quiet) < audio.MID_VERSION_THRESHOLD
    storage.save_bigness({search_module.track_key("Band B", "Yellow"): quiet})

    app.session_state["candidates"] = [
        track("Band A", "Yellow (Epic Trailer Version)", "a"),
        track("Band B", "Yellow", "b"),
    ]
    app.run()

    assert not app.exception
    row = [p for p in app.pills if p.key == "bucket_filter"]
    assert row, "שורת הקטגוריות לא הוצגה"
    # התוויות עוברות דרך `format_func`, ולכן הן "Intimate (1)" ולא השם לבדו
    assert any(str(option).startswith(buckets.INTIMATE) for option in row[0].options), \
        "מדידה שהייתה בקאש לא הגיעה לשורת הקטגוריות באותה ריצה"


def test_the_category_row_is_hidden_when_there_is_nothing_to_narrow(app):
    """שורת כפתורים עם קטגוריה אחת היא רעש: היא לא מציעה שום בחירה."""
    app.session_state["candidates"] = [
        track("Band A", "Yellow (Metal Cover)", "a"),
        track("Band B", "Yellow (Rock Cover)", "b"),
    ]
    app.run()

    assert not app.exception
    assert not [p for p in app.pills if p.key == "bucket_filter"]


def test_the_strongest_cover_stays_at_the_top_of_the_list(app):
    """ההבטחה שהמסך עצמו נותן. פיצול לקטגוריות שבר אותה, ולכן הקטגוריות
    הן מסנן: גרסת טריילר מדורגת ראשונה גם כשקאבר אחר נמדד רועש יותר."""
    app.session_state["candidates"] = [
        track("Plain Band", "Yellow", "plain"),
        track("Epic Band", "Yellow (Epic Trailer Version)", "epic"),
    ]
    app.session_state["bigness"] = {
        "itunes-plain": {"loudness": 0.30, "low_end": 3.0,
                         "onset_rate": 3.5, "dynamic_span": 6.0},
    }
    app.run()

    assert not app.exception
    order = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert order.index("btn_favorite_itunes-epic") < order.index("btn_favorite_itunes-plain")


def test_the_same_work_filter_keeps_only_catalogue_verified_versions(app):
    """"Brenda Lee - I'm Sorry" החזיר גם שירים אחרים באותו שם, כי החיפוש
    בחנויות מתאים לפי שם בלבד."""
    same = track("Slow Cover", "I'm Sorry", "a")
    same["work_verified"] = True
    other = track("Other Band", "I'm Sorry", "b")
    other["work_verified"] = False
    app.session_state["candidates"] = [same, other]
    app.run()

    box = [c for c in app.checkbox if "Verified same work" in c.label]
    assert box, "אין פילטר לגרסאות של אותה יצירה"
    box[0].check().run()

    assert not app.exception
    shown = _rendered(app)
    assert "Slow Cover" in shown
    assert "Other Band" not in shown


def test_the_same_work_filter_does_not_empty_results_it_cannot_verify(app):
    """"Covers of an artist", "עוד כמו זה" והחיפוש החופשי אינם עוברים דרך הקטלוג,
    ולכן אין להם `work_verified` — וסינון עליו רוקן את הרשימה עד
    "מוצגים 0 מתוך 0"."""
    app.session_state["candidates"] = [track("2WEI", "Zombie", "a"),
                                       track("Hidden Citizens", "Alive", "b")]
    app.run()
    [c for c in app.checkbox if "Verified same work" in c.label][0].check().run()

    assert not app.exception
    shown = _rendered(app)
    assert "2WEI" in shown and "Hidden Citizens" in shown
    assert any("Catalogue verification only exists" in c.value for c in app.caption), \
        "הפילטר לא סינן — וצריך להגיד למה"


def test_the_playlist_offers_to_refresh_dead_preview_links(app):
    """כתובת preview היא כתובת CDN: גרסה ששמורה חודשים יכולה להצביע על
    קובץ שכבר לא קיים, וכפתור הנגינה שלה פשוט לא מנגן."""
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")

    assert not app.exception
    assert any("Refresh playback links" in b.label for b in app.button)


def test_a_missing_link_is_a_refresh_candidate_like_a_stale_one():
    """הבחירה מופרדת מהרשת בדיוק כדי שתיבדק בלי רשת.

    ההבדל בין כתובת חיה למתה הוא המקור ולא הגיל: אצל Deezer היא חתומה
    וקצרת-מועד, אצל iTunes ארוכת-מועד — וזה מסביר למה באותה קבוצה, שנשמרה
    באותו זמן, חלק מנגן וחלק לא.

    **רשומה בלי כתובת כלל היא מועמדת גם היא**, וזה שינוי מכוון: קודם היא
    דולגה, ולכן גרסה שכתובתה מתה נשארה אפורה לנצח. היא לא נבדקת בכל
    כניסה — כישלון גם הוא כותב `preview_checked_at`, ואותו TTL שולט בה.
    """
    import app as app_module

    now = 1_700_000_000.0
    hour, day = 3600.0, 86400.0
    favorites = {
        "deezer-fresh": {"source": "Deezer", "preview_url": "u",
                         "preview_checked_at": now - hour},
        "deezer-stale": {"source": "Deezer", "preview_url": "u",
                         "preview_checked_at": now - 8 * hour},
        "itunes-fresh": {"source": "iTunes", "preview_url": "u",
                         "preview_checked_at": now - 2 * day},
        "itunes-stale": {"source": "iTunes", "preview_url": "u",
                         "preview_checked_at": now - 40 * day},
        "never-checked": {"source": "iTunes", "preview_url": "u"},
        "no-preview": {"source": "iTunes", "preview_url": ""},
        "corrupt-stamp": {"source": "iTunes", "preview_url": "u",
                          "preview_checked_at": "לא מספר"},
    }

    stale = set(app_module._stale_previews(favorites, now=now))
    assert stale == {"deezer-stale", "itunes-stale", "never-checked",
                     "corrupt-stamp", "no-preview"}


def test_the_automatic_refresh_is_capped_and_finishes_next_time():
    """מעבר אחד לא חוסם את הסרגל על פלייליסט ענק; השאר נבחר במעבר הבא."""
    import app as app_module

    now = 1_700_000_000.0
    favorites = {f"k{index}": {"source": "Deezer", "preview_url": "u"}
                 for index in range(60)}
    picked = app_module._stale_previews(favorites, now=now, cap=40)
    assert len(picked) == 40

    for key in picked:
        favorites[key]["preview_checked_at"] = now
    assert len(app_module._stale_previews(favorites, now=now, cap=40)) == 20


def test_the_playlist_refreshes_dead_previews_by_itself_once(tmp_path, monkeypatch):
    """הלב של התיקון: המשתמש לא צריך להבחין בכפתור אפור וללחוץ על משהו.
    ואסור שזה ירוץ שוב בכל rerun — אחרת כל לחיצה באפליקציה היא סבב רשת.
    """
    import json
    import search as search_module

    calls = {"n": 0}

    def fake_refresh(entry, client=None):
        calls["n"] += 1
        return f"http://new/{entry['uid']}.mp3", entry["uid"]

    monkeypatch.setattr(search_module, "refresh_preview", fake_refresh)
    saved = {f"a{i}|t{i}": {"artist": f"A{i}", "track": f"T{i}", "source": "Deezer",
                            "preview_url": f"http://old/{i}.mp3", "uid": f"deezer-{i}",
                            "features": None, "added_at": 1.0}
             for i in range(5)}
    (tmp_path / "favorites.json").write_text(json.dumps(saved), encoding="utf-8")

    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["rail_nav"] = "Loved"
    at.run()

    assert not at.exception
    assert calls["n"] == 5, "לא כל הכתובות המתות רועננו"
    on_disk = json.loads((tmp_path / "favorites.json").read_text(encoding="utf-8"))
    assert all(entry["preview_url"].startswith("http://new/") for entry in on_disk.values())
    assert all(entry.get("preview_checked_at") for entry in on_disk.values())

    at.run()
    assert calls["n"] == 5, "המעבר האוטומטי חוזר על עצמו בכל rerun"


def test_a_failed_resolution_keeps_the_url_it_had(app, monkeypatch):
    """כתובת ישנה שאולי עובדת עדיפה על שדה ריק: תקלת רשת חד-פעמית לא
    מרוקנת את הפלייליסט."""
    import app as app_module
    import search as search_module

    monkeypatch.setattr(search_module, "refresh_preview", lambda e, client=None: ("", ""))
    favorites = {"k": {"artist": "2WEI", "track": "Zombie", "source": "Deezer",
                       "preview_url": "http://old/preview.mp3"}}
    try:
        app_module.refresh_previews(favorites, keys=["k"], quiet=True)
    except Exception:
        pass          # st.rerun מחוץ להקשר של סקריפט
    assert favorites["k"]["preview_url"] == "http://old/preview.mp3"
    # ונרשמה כנבדקה, אחרת אותה רשומה נבדקת שוב בכל rerun
    assert favorites["k"]["preview_checked_at"] > 0


def test_a_refresh_that_found_nothing_says_so(tmp_path, monkeypatch):
    """כישלון שקט הוא מה שהחזיר את הבאג הזה שוב ושוב: המשתמש ראה ספינר,
    אחריו כפתורים אפורים, ובלי מילה אחת של הסבר."""
    import json
    import search as search_module

    monkeypatch.setattr(search_module, "refresh_preview", lambda e, client=None: ("", ""))
    saved = {f"a{i}|t{i}": {"artist": f"A{i}", "track": f"T{i}", "source": "Deezer",
                            "preview_url": f"http://old/{i}.mp3", "uid": f"deezer-{i}",
                            "features": None, "added_at": 1.0}
             for i in range(3)}
    (tmp_path / "favorites.json").write_text(json.dumps(saved), encoding="utf-8")

    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["rail_nav"] = "Loved"
    at.run()

    assert not at.exception
    # כולן נכשלו — זו כמעט תמיד תקלת רשת, ולכן אזהרה ולא הערה בשוליים
    assert at.warning, "ריענון שלא מצא כלום עבר בשקט"
    assert "3" in at.warning[0].value
    # והכתובות הישנות נשמרו
    on_disk = json.loads((tmp_path / "favorites.json").read_text(encoding="utf-8"))
    assert all(e["preview_url"].startswith("http://old/") for e in on_disk.values())


def test_a_partial_refresh_failure_says_nothing_at_all(tmp_path, monkeypatch):
    """כשרק חלק נכשלו זה כנראה גרסאות שנמחקו מהחנות, לא תקלת רשת.

    קודם הוצגה כאן ספירה ("כך וכך לא נמצאו"). היא ירדה לבקשת המשתמש:
    עם פלייליסט גדול תמיד יש כמה גרסאות שנמחקו, ולכן היא הופיעה כמעט בכל
    כניסה — דיווח מצב שאי אפשר לעשות איתו דבר, בזמן שהכפתור האפור בשורה
    כבר אומר בדיוק את זה. כשל **מוחלט** עדיין מדבר; ראו
    `test_a_refresh_that_found_nothing_says_so`.
    """
    import json
    import search as search_module

    def half(entry, client=None):
        return ("http://new/x.mp3", entry["uid"]) if entry["uid"].endswith("0") else ("", "")

    monkeypatch.setattr(search_module, "refresh_preview", half)
    saved = {f"a{i}|t{i}": {"artist": f"A{i}", "track": f"T{i}", "source": "Deezer",
                            "preview_url": f"http://old/{i}.mp3", "uid": f"deezer-{i}",
                            "features": None, "added_at": 1.0}
             for i in range(3)}
    (tmp_path / "favorites.json").write_text(json.dumps(saved), encoding="utf-8")

    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["rail_nav"] = "Loved"
    at.run()

    assert not at.exception
    assert not at.warning, "כישלון חלקי אינו תקלת רשת ואינו מצדיק אזהרה"
    _said = " ".join(str(c.value) for c in at.caption if c.value)
    assert "live link" not in _said, "הריענון אמור להיות שקט"
    assert "greyed out" not in _said, "הספירה ירדה — הכפתור האפור אומר את זה בעצמו"


def test_a_saved_version_records_when_its_preview_was_checked(app):
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")

    saved = list(app.session_state["favorites"].values())[0]
    assert saved["preview_checked_at"] > 0


def test_the_refresh_button_sits_above_the_saved_groups(app):
    """עם שבעים גרסאות מכווצות הוא ישב מתחת לכל הרשימה וגם מתחת לייצוא,
    ולא נמצא — בדיוק כשכפתור נגינה מפסיק לנגן."""
    for index in range(3):
        _save(app, f"Artist{index}", f"Song {index} (Epic Trailer Version)", f"k{index}",
              searched=f"Song {index}")

    labels = [b.label for b in app.button]
    groups = [b.label for b in app.get("expander")]
    assert "Refresh playback links" in labels
    refresh_at = labels.index("Refresh playback links")
    opens = [labels.index(l) for l in labels
             if l and l.startswith("Artist")]
    assert groups, "אין קבוצות בפלייליסט"
    assert all(refresh_at < position for position in opens), \
        "כפתור הריענון יושב אחרי הגרסאות השמורות"


def test_a_saved_version_keeps_its_source_id_so_it_can_be_refreshed(app):
    """בלי `uid` אי אפשר לפנות שוב לחנות על הגרסה הזו."""
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")

    saved = list(app.session_state["favorites"].values())[0]
    assert saved["uid"] == "itunes-a"


def test_a_saved_version_plays_from_the_sidebar_in_one_tap(app):
    """קודם הנגן ישב בתוך popover: הקשה אחת פתחה חלון שכל תוכנו כפתור
    נגינה, והקשה שנייה ניגנה."""
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")

    assert not app.exception
    html = " ".join(str(e.proto) for e in app.get("html"))
    assert "ts-play" in html and "<audio" in html
    popovers = " ".join(str(b.proto) for b in app.get("popover"))
    assert "play_arrow" not in popovers, "אין צורך בחלון בדרך אל כפתור הנגינה"


def test_a_song_name_never_reaches_raw_html(app):
    """שמות שירים מגיעים מקטלוג חיצוני, ולכן אסור להם להגיע ל-`st.html`."""
    _save(app, "2WEI", "<img src=x onerror=alert(1)> (Epic Version)", "a",
          searched="<img src=x onerror=alert(1)>")

    assert not app.exception
    raw = " ".join(str(e.proto) for e in app.get("html"))
    assert "<img src=x" not in raw


def test_the_playlist_groups_start_collapsed(app):
    """שבעים גרסאות שמורות פרושות הן סרגל שאי אפשר לגלול בו אל שום דבר."""
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")
    _save(app, "Tommee Profitt", "In the End (Dark Cover)", "b", searched="In the End")

    assert not app.exception
    groups = app.get("expander")
    assert len(groups) >= 2
    assert not any(b.proto.expanded for b in groups), "כל הקבוצות מכווצות"


def test_the_group_label_is_the_song_and_the_artist(app):
    """כותרת הקבוצה היא שיר המקור, ולא שם אחת הגרסאות שבתוכה.

    (הבידוד הדו-כיווני `\u2068…\u2069` שהיה כאן קודם היה תיקון RTL: בלעדיו
    "Heroes" ו-"5 גרסאות" נקראו הפוך בטלפון. הממשק אנגלי ו-LTR, ואין לו
    מה לבודד.)
    """
    _save(app, "2WEI", "Heroes (Epic Trailer Version)", "a", searched="Heroes")
    _save(app, "Hidden Citizens", "Heroes (Cover)", "b", searched="Heroes")

    labels = " ".join(str(b.proto) for b in app.get("expander"))
    assert "Heroes · The Verve" in labels
    assert "Epic Trailer Version" not in labels


def test_removing_the_last_version_removes_the_group(app):
    _save(app, "2WEI", "Bitter Sweet Symphony (Epic Trailer Version)", "a")
    key = list(app.session_state["favorites"])[0]

    app.button(key=f"unfav_{key}").click().run()

    assert not app.exception
    assert app.session_state["favorites"] == {}
    headers = " ".join(str(b.proto) for b in app.get("expander"))
    assert "Bitter Sweet Symphony" not in headers


# ---------- קישור ל-YouTube Music ----------

def test_the_track_name_links_to_youtube_music(app):
    """התצוגה המקדימה היא 30 שניות; שם השיר הוא המסלול לגרסה המלאה."""
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    assert not app.exception
    rendered = _rendered(app)
    assert "music.youtube.com/search?q=" in rendered
    assert "2WEI+Zombie" in rendered, "השאילתה חייבת לכלול אמן ושיר"


def test_brackets_in_a_track_name_do_not_break_the_link(app):
    """"Yellow [Radio Edit]" היה שובר את תחביר הקישור ב-markdown."""
    app.session_state["candidates"] = [track("Coldplay", "Yellow [Radio Edit]", "b1")]
    app.run()

    assert not app.exception
    # הכותרת עוברת דרך `html.escape` ולא דרך תחביר קישור של markdown,
    # ולכן סוגריים מרובעים אינם יכולים לשבור את הקישור מלכתחילה
    rendered = _rendered(app)
    assert "[Radio Edit]" in rendered and "music.youtube.com" in rendered


# ---------- הנגן ----------

def test_the_player_is_ours_and_still_a_real_audio_element(app):
    """`st.audio` נראה כמו הדפדפן ולא כמו האפליקציה. אלמנט אודיו אמיתי
    נשאר, כי הוא מה שמשמר "רק נגן אחד בכל רגע"."""
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    html = " ".join(str(e.proto) for e in app.get("html"))
    assert "ts-player" in html and "ts-play" in html
    assert "<audio" in html and "preload=" in html


def test_the_result_row_keeps_the_css_hook_for_narrow_screens(app):
    """ב-390px העטיפה ועמודת הציון השאירו לכותרת 124px — שליש מהרוחב —
    ושם ארוך נשבר לשבע שורות. ה-key הוא מה שמאפשר ל-CSS לסדר מחדש את
    השורה בטלפון, ולתת לנגינה וללב יעדי מגע של 44px."""
    import pathlib

    import app as app_module

    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    css = " ".join(str(e.proto) for e in app.get("markdown")
                   if "st-key-trow_" in str(e.proto))
    assert css, "כלל ה-CSS לשורת התוצאה בטלפון נעלם"
    assert "st-key-tacts_" in css, "כלל ה-CSS לעמודת הפעולות בטלפון נעלם"
    # AppTest אינו חושף מכולות רגילות ואת המפתחות שלהן, ולכן הצד השני של
    # הצמד נבדק על המקור: כלל CSS בלי המפתח שהוא תופס הוא כלל מת
    source = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    assert 'key=f"trow_' in source, "המכולה כבר לא נושאת את ה-key"
    assert 'key=f"tacts_' in source, "מכולת הפעולות כבר לא נושאת את ה-key"


def test_the_page_has_one_audio_element_for_all_the_players(app):
    """Safari לנייד מגביל כמה אלמנטי מדיה ייטענו בדף; פלייליסט של שבעים
    גרסאות ייצר שבעים, ומעבר לתקרה הם פשוט לא ניגנו."""
    app.session_state["candidates"] = [track("2WEI", f"Zombie {i}", f"e{i}")
                                       for i in range(12)]
    app.run()

    assert not app.exception
    raw = " ".join(str(e.proto) for e in app.get("html"))
    assert raw.count("<audio") == 1, "אלמנט אודיו אחד לכל הדף"
    assert raw.count("ts-play") >= 12, "כפתור נגינה לכל גרסה"


def test_each_play_button_carries_its_own_identity(app):
    """לפי הכתובת לבדה שתי שורות של אותה גרסה היו נדלקות יחד."""
    app.session_state["candidates"] = [track("2WEI", "Zombie", "e1"),
                                       track("Hidden Citizens", "Zombie", "e2")]
    app.run()

    raw = " ".join(str(e.proto) for e in app.get("html"))
    assert "data-id=" in raw and "data-src=" in raw


def test_the_player_is_a_play_button_with_nothing_around_it(app):
    """תצוגה מקדימה של שלושים שניות לא צריכה פס התקדמות ושעון — ובסרגל
    הצר הם היו רוב הרוחב של השורה."""
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    # `ts-bar` הוא היום סרגל הנגן התחתון ולכן הוא **אמור** להיות בדף;
    # מה שנבדק כאן הוא שהשורה עצמה לא הצמיחה פס התקדמות ושעון
    html = " ".join(str(e.proto) for e in app.get("html"))
    assert "ts-progress" not in html and "ts-time" not in html
    assert "<progress" not in html


def test_the_audio_element_is_not_removed_from_the_render_tree(app):
    """`display: none` על אלמנט מדיה הוא מקור ידוע לסירובי נגינה
    ב-Safari לנייד; ההסתרה חייבת להשאיר אותו בעץ."""
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    css = " ".join(str(e.proto) for e in app.get("markdown") if "ts-player" in str(e.proto))
    assert ".ts-player audio" in css
    rule = css.split(".ts-player audio")[1].split("}")[0]
    assert "display: none" not in rule
    assert "opacity: 0" in rule


def test_the_player_behaviour_is_delegated_not_bound_per_player(app):
    """הכרטיסים נבנים מחדש בכל rerun, וה-iframe אינו מורכב מחדש — סקריפט
    שמתחבר לכל נגן בנפרד לא ימצא אף נגן שנוצר אחריו."""
    script = " ".join(str(e.proto) for e in app.get("iframe"))
    assert "__audioBehaviourBound" in script
    assert "ts-play" in script and "addEventListener" in script


def test_the_player_script_runs_in_the_page_and_not_in_the_iframe(app):
    """ב-Safari לנייד ההרשאה לנגן נבדקת מול ההקשר שממנו נקראה `play()`;
    קריאה מתוך iframe מוצלב-מקור היא בדיוק המקרה שנחסם."""
    script = " ".join(str(e.proto) for e in app.get("iframe"))
    assert "createElement(\\\"script\\\")" in script or "createElement('script')" in script
    assert "doc.head.appendChild" in script


def test_the_playlist_is_a_rail_screen_and_the_blacklist_is_not(app):
    """הפלייליסט הוא פריט ניווט; הרשימה השחורה ירדה לתוך ההגדרות.

    קודם שניהם היו זה מתחת לזה באותו סרגל, והסרגל היה עמוד שני שגוללים
    בו במקום ניווט.
    """
    _nav(app, "Loved")
    rendered = _rendered(app)
    assert "loved cover" in rendered
    assert "Blocked artists" not in rendered

    _nav(app, "Settings")
    assert "Blocked artists" in " ".join(str(b.proto) for b in app.get("expander"))


# ---------- עדות טריילר בדירוג ----------

def _epic(uid="epic"):
    return track("2WEI", "Zombie (Epic Trailer Version)", uid,
                 album="Epic Covers", genre="Soundtrack")


def _plain(uid="plain"):
    return track("Some Band", "Zombie", uid, album="Greatest Hits", genre="Pop")


def test_an_unmeasured_epic_version_outranks_a_measured_loud_cover(app):
    """התלונה: "מלא שירים שרשום עליהם טריילר epic ועדיין הם תחתונים".

    המפתח הקודם היה `(taste, measured_size, score)` לקסיקוגרפית. בלי לייקים
    הטעם היה 0 לכולם, ולכן הגודל הנמדד הכריע לבדו — ו"טרם נמדד" היה 1-,
    כלומר תחתית הרשימה. הטראק כאן נושא שני סימני טריילר וציון 130 מול 100,
    והוא דורג אחרון.
    """
    app.session_state["candidates"] = [_epic(), _plain()]
    app.session_state["bigness"] = {"itunes-plain": BIG}
    app.run()

    assert not app.exception
    assert _row_order(app)[0] == "itunes-epic"


def test_a_quiet_epic_version_outranks_a_loud_plain_cover(app):
    """גרסה תזמורתית יכולה להימדד שקטה בקטע של 30 שניות. זה לא הופך אותה
    לפחות טריילרית."""
    app.session_state["candidates"] = [_epic(), _plain()]
    app.session_state["bigness"] = {"itunes-epic": SMALL, "itunes-plain": BIG}
    app.run()

    assert not app.exception
    assert _row_order(app)[0] == "itunes-epic"


def test_a_verified_cover_is_not_buried_under_generic_declared_cues(app):
    """התלונה: גרסת טריילר טובה במקום 1, אחריה שמונה-עשרה קיו-ים גנריים
    מספריות הפקה, ובמקום 20 קאבר אמיתי ומצוין.

    ספריות הפקה מכריזות על עצמן כטריילר בהגדרה — זה המוצר שלהן — ולכן
    `trailer_strength` הטה רבע מהדירוג לטובתן. `work_verified` הוא האות
    שמפריד: הקטלוג פותר את היצירה, וקיו בשם "Stayin' Alive Epic Trailer"
    אינו גרסה שלה.
    """
    cues = []
    for index in range(18):
        cue = track(f"LibraryCue{index}", f"Stayin' Alive Epic Trailer {index}",
                    f"c{index}", album="Epic Trailer Music Vol 3", genre="Soundtrack")
        cue["work_verified"] = False
        cues.append(cue)
    declared = track("2WEI", "Stayin' Alive (Epic Trailer Version)", "good",
                     genre="Soundtrack")
    declared["work_verified"] = True
    real = track("Oskura", "Stayin' Alive (Bee Gees Cover)", "oskura",
                 album="Only Time to Dream")
    real["work_verified"] = True

    app.session_state["candidates"] = cues + [declared, real]
    app.session_state["bigness"] = {
        **{f"itunes-c{i}": BIG for i in range(18)},
        "itunes-good": BIG, "itunes-oskura": SMALL,
    }
    app.run()

    assert not app.exception
    order = _row_order(app)
    assert order[0] == "itunes-good", "גרסה מוכרזת ומאומתת נשארת ראשונה"
    assert "itunes-oskura" in order[:3], \
        f"הקאבר המאומת נקבר מתחת לקיו-ים הגנריים: מקום {order.index('itunes-oskura') + 1}"


def test_without_catalogue_verification_the_order_is_unchanged(app):
    """ב"Covers of an artist", "עוד כמו זה" ובחיפוש החופשי אף תוצאה אינה נושאת את
    השדה — הרכיב קבוע לכולם, ולכן אסור לו לשנות דבר."""
    app.session_state["candidates"] = [_plain(), _epic()]
    app.session_state["bigness"] = {"itunes-plain": BIG}
    app.run()

    assert not app.exception
    assert _row_order(app)[0] == "itunes-epic"


def test_the_overflow_menu_speaks_in_words_not_in_debug_output(app):
    """התלונה, עם צילום מהטלפון: "עדיין יש מלא קישקושי html". ב-⋯ ישבו
    שלוש שורות של מספרים גולמיים (rank 0.239 · taste 17% · trailer 0.67
    · loudness 0.22 · low end ×0.62 · hits 2.4/s), שהם כלי כיול שדלף
    למוצר. מה שנשאר הוא מה שבאמת מכריע: האם הקטלוג מאשר את הגרסה."""
    verified = _epic()
    verified["work_verified"] = True
    verified["album"] = "Cinematic Covers"
    app.session_state["candidates"] = [verified]
    app.run()

    captions = [c.value for c in app.caption]
    assert any("Confirmed version of this song" in text and "Cinematic Covers" in text
               for text in captions), "אין שורת סיכום קריאה ב-⋯"
    for noise in ("rank 0.", "taste 1", "trailer 0.", "low end", "hits ", "relevance:"):
        assert not any(noise in text for text in captions), noise


def test_an_unconfirmed_row_says_so_in_the_overflow_menu(app):
    """הסימן היחיד ששרד הוא זה שמפריד בין גרסה של השיר שביקשת לבין שיר
    אחר באותו שם, ולכן הוא חייב להיקרא בשני הכיוונים."""
    unverified = _epic()
    unverified["work_verified"] = False
    app.session_state["candidates"] = [unverified]
    app.run()

    assert any("Not confirmed in the catalogue" in (c.value or "")
               for c in app.caption)


def test_the_reason_shown_is_the_reason_it_ranks(app):
    """הדירוג נספר מאותם סימנים שמוצגים בשורה, ולא ממדד נסתר."""
    import search as search_module

    assert search_module.trailer_strength(_epic()) > search_module.trailer_strength(_plain())
    app.session_state["candidates"] = [_epic()]
    app.run()
    tags = " ".join(str(e.proto) for e in app.get("html") if "ts-tag" in str(e.proto))
    assert "EPIC" in tags and "SOUNDTRACK" in tags


def test_a_one_letter_artist_is_not_a_trailer_artist():
    """`partial_ratio` מחזיר 100 על אות בודדת: האמן "X" נמצא זהה ל-"Extreme
    Music". כשזה הפך לסימן מוצג ולמשקל בדירוג, הבאג נעשה גלוי."""
    import search as search_module

    assert not search_module.is_trailer_artist({"artist": "X"})
    assert not search_module.is_trailer_artist({"artist": "The Verve"})
    assert search_module.is_trailer_artist({"artist": "2WEI"})
    assert search_module.is_trailer_artist({"artist": "Tommee Profitt"})


# ---------- יציבות הסדר ----------

BIG = {"loudness": 0.30, "low_end": 3.0, "onset_rate": 3.5, "dynamic_span": 6.0}
SMALL = {"loudness": 0.08, "low_end": 0.8, "onset_rate": 0.8, "dynamic_span": 1.5}


def _row_order(app) -> list:
    return [(b.key or "").replace("btn_favorite_", "")
            for b in app.button if (b.key or "").startswith("btn_favorite_")]


def _thirty(genre_of=lambda i: "Soundtrack"):
    return [track(f"A{i}", f"T{i}", f"u{i}", score=100 - i, genre=genre_of(i))
            for i in range(30)]


# פרופילי כרומה מ-`tests/test_bigness.py` — משולש מז'ורי, אותו משולש
# מועבר טונציה (אותו שיר בסולם אחר), ומבנה מרווחים אחר לגמרי
_TRIAD = [.20, .02, .05, .02, .18, .05, .02, .19, .02, .06, .03, .04]
_TRANSPOSED = _TRIAD[-2:] + _TRIAD[:-2]
_CLUSTER = [.20, .19, .18, .02, .03, .02, .02, .03, .02, .06, .03, .04]


def test_the_harmonic_match_to_the_reference_moves_the_order(app):
    """הסימן שעובד גם כששום מאגר לא מכיר את השיר: שני קאברים זהים בכל
    השאר, אחד מהם חולק מהלך הרמוני עם גרסת הייחוס (בטונציה אחרת) והשני
    לא — והראשון עולה."""
    same_song = track("Cover A", "T", "match", preview_url="http://p")
    other_song = track("Cover B", "T", "nomatch", preview_url="http://p")
    app.session_state["candidates"] = [other_song, same_song]
    app.session_state["original"] = {
        "artist": "Origin", "track": "T", "uid": "itunes-ref", "preview_url": ""}
    app.session_state["bigness"] = {
        "itunes-ref": {**SMALL, "chroma": _TRIAD},
        "itunes-match": {**SMALL, "chroma": _TRANSPOSED},
        "itunes-nomatch": {**SMALL, "chroma": _CLUSTER},
    }
    app.run()

    assert not app.exception
    assert _row_order(app) == ["itunes-match", "itunes-nomatch"]


def test_without_a_measured_reference_the_harmony_term_changes_nothing(app):
    """גרסת ייחוס בלי preview לא נמדדת לעולם, ואז הרכיב חייב להיות קבוע
    לכולם — ולא להעניש בשקט את מי שכן נמדד."""
    import audio as audio_module

    first = track("A", "T", "a", preview_url="http://p")
    second = track("B", "T", "b", preview_url="http://p")
    app.session_state["candidates"] = [first, second]
    app.session_state["original"] = None
    app.session_state["bigness"] = {"itunes-a": {**SMALL, "chroma": _TRIAD}}
    app.run()

    assert not app.exception
    assert audio_module.chroma_similarity({**SMALL, "chroma": _TRIAD}, None) is None
    assert set(_row_order(app)) == {"itunes-a", "itunes-b"}


def test_arriving_measurements_do_not_move_the_rows(app):
    """התלונה: "כל פעם שאני מנגן או לוחץ הכל קופץ".

    מדידות האודיו חוזרות מהדפדפן שניות אחרי שהתוצאות כבר על המסך, והן מפתח
    המיון הראשי. לפני ההקפאה נמדד שכל 20 השורות הנראות משנות מיקום ברגע
    שהמדידות נכנסות.
    """
    app.session_state["candidates"] = _thirty()
    app.run()
    before = _row_order(app)

    app.session_state["bigness"] = {f"itunes-u{i}": (BIG if i in (5, 17, 19) else SMALL)
                                    for i in range(20)}
    app.run()

    assert not app.exception
    assert _row_order(app) == before


def test_a_single_heart_does_not_push_songs_off_the_page(app):
    """התלונה: "שירים נעלמים".

    הם לא נמחקו — הדירוג מחדש דחף אותם אל מעבר ל-20 המוצגים. לפני ההקפאה
    לחיצת ❤️ אחת הוציאה שלושה שירים מהחלון הנראה.
    """
    app.session_state["candidates"] = _thirty(
        lambda i: "Metal" if i in (23, 27, 28) else "Soundtrack")
    app.run()
    before = _row_order(app)

    app.session_state["favorites"] = {
        "a23|t23": {"artist": "A23", "track": "T23", "genre": "Metal",
                    "features": None, "added_at": 1_700_000_000.0}}
    app.run()

    assert not app.exception
    assert _row_order(app) == before


def test_changing_the_sort_still_reorders(app):
    """ההקפאה לא הפכה את בורר המיון למת."""
    app.session_state["candidates"] = _thirty()
    app.run()
    before = _row_order(app)

    picker = [s for s in app.selectbox if s.key == "sort_by"][0]
    picker.set_value("Artist").run()

    assert not app.exception
    assert _row_order(app) != before
    # מיון לפי אמן: A0, A1, A10, A11 … לקסיקוגרפי ולא מספרי
    assert _row_order(app)[:3] == ["itunes-u0", "itunes-u1", "itunes-u10"]


def test_a_new_search_recomputes_the_order(app, monkeypatch):
    """ההקפאה חלה בתוך רשימה קיימת, לא בין חיפושים."""
    app.session_state["candidates"] = _thirty()
    app.run()
    generation = app.session_state["result_generation"]

    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: ([track("New", "Fresh", "n1")], "src", None))
    app.text_input(key="cover_title").set_value("Fresh").run()
    [b for b in app.button if b.key == "btn_search"][0].click().run()

    assert not app.exception
    assert app.session_state["result_generation"] > generation
    assert _row_order(app) == ["itunes-n1"]


def test_blocking_an_artist_drops_it_without_moving_the_rest(app):
    app.session_state["candidates"] = _thirty()
    app.run()
    before = _row_order(app)

    app.button(key="btn_block_itunes-u3").click().run()

    assert not app.exception
    after = _row_order(app)
    assert "itunes-u3" not in after
    assert after == [uid for uid in before if uid != "itunes-u3"] + ["itunes-u20"]


def test_a_row_without_a_preview_says_so_instead_of_just_hiding_the_button(app):
    """`.ts-noplay` כבר מסמן את זה ב-`title`, אבל זה טקסט שרואים רק
    ב-hover ולא בסריקה של הרשימה."""
    silent = track("No Preview Band", "Quiet One", "np1", preview_url="")
    playable = track("Loud Band", "Loud One", "p1")
    app.session_state["candidates"] = [silent, playable]
    app.run()

    bodies = _html_bodies(app)
    assert "no preview" in bodies
    # התג לא נדבק לשורה שכן מנגנת
    assert bodies.count("no preview") == 1


def test_reporting_a_wrong_song_removes_it_and_is_remembered_next_search(app, monkeypatch):
    """"give me a report option — not the right song. make the algoritem
    learn": הדיווח מוריד את הטראק מיד, ונשמר כדי שגם החיפוש הבא לאותו
    שיר ידלג עליו — גם אם המקור עצמו יציע אותו שוב."""
    wrong = track("J2", "Closer (feat. Keeley Bumford) [Epic Trailer Version]", "w1")
    right = track("Glee Cast", "Loser (Glee Cast Version)", "r1")
    app.session_state["candidates"] = [wrong, right]
    app.session_state["original"] = {"artist": "Beck", "track": "Loser", "year": "1993"}
    app.run()

    reports = [b for b in app.button if b.key == "btn_report_itunes-w1"]
    assert reports, "the report action should show once an original song is known"
    reports[0].click().run()

    assert not app.exception
    assert "itunes-w1" not in _row_order(app)
    assert "itunes-r1" in _row_order(app)

    wrong_key = search_module.track_key("J2", wrong["track"])
    assert storage.load_mismatch_reports() == {
        search_module.track_key("Beck", "Loser"): {wrong_key}}

    # חיפוש חדש לאותו שיר, שהמקור (ללא קשר לדיווח) מציע בו את אותה
    # התאמה שגויה שוב — ועדיין לא רואים אותה
    monkeypatch.setattr(
        covers, "find_all_covers",
        lambda title, artist="", **k: ([wrong, right], "src",
                                       {"artist": "Beck", "track": "Loser"}))
    app.text_input(key="cover_title").set_value("Loser").run()
    app.text_input(key="cover_artist").set_value("Beck").run()
    [b for b in app.button if b.key == "btn_search"][0].click().run()

    assert not app.exception
    assert _row_order(app) == ["itunes-r1"]


def test_the_report_action_is_absent_without_a_known_original_song(app):
    """חיפוש חופשי אינו פותר שיר מקור יחיד — אין למה לקשור את הדיווח,
    ולכן הכפתור לא מופיע במקום לדווח תחת מפתח שגוי."""
    app.session_state["candidates"] = [track("X", "Anything", "x1")]
    app.session_state["original"] = None
    app.run()
    assert not [b for b in app.button if b.key == "btn_report_itunes-x1"]


def test_the_resort_control_never_appears_or_disappears(app):
    """כפתור שצץ מעל הרשימה דוחף את כל מה שמתחתיו — וזה מזיז את המקום.

    לכן הוא מצויר תמיד, ומושבת כשאין מה לסדר.
    """
    app.session_state["candidates"] = _thirty()
    app.run()
    quiet = [b for b in app.button if (b.label or "").startswith(("Re-sort", "Order is up to date"))]
    assert len(quiet) == 1 and quiet[0].disabled

    app.session_state["bigness"] = {f"itunes-u{i}": (BIG if i in (5, 17, 19) else SMALL)
                                    for i in range(20)}
    app.run()
    active = [b for b in app.button if (b.label or "").startswith(("Re-sort", "Order is up to date"))]
    assert len(active) == 1 and not active[0].disabled
    assert "will move" in active[0].label


def test_the_scroll_keeper_is_a_persistent_observer(app):
    """נמדד ש-iframe לא מורכב מחדש ב-rerun, ולכן סקריפט-בטעינה לא נורה.

    השומר חייב להיות MutationObserver שחי בדף, ולשחזר רק את הצירוף
    "היינו עמוק בעמוד ואחרי בנייה מחדש אנחנו בראשו".
    """
    script = " ".join(str(e.proto) for e in app.get("iframe"))
    assert "MutationObserver" in script
    assert "saved > 200 && el.scrollTop < 40" in script


def test_a_generation_marker_lets_the_keeper_forget_the_old_list(app):
    app.session_state["candidates"] = _thirty()
    app.run()
    generation = app.session_state["result_generation"]
    assert any(f"data-result-generation='{generation}'" in (m.value or "")
               for m in app.markdown)


def test_taste_lifts_tracks_that_match_what_was_hearted(app):
    """הבדיקה שקובעת, ובכוונה נגד מיון הגודל.

    המשתמש אוהב גרסאות *רגועות*. מיון "גודל נמדד" היה מציב את הרועשת ראשונה
    תמיד — ולכן אם הרגועה עולה, זה יכול לנבוע רק מהלמידה.
    """
    loud = {"loudness": 0.29, "low_end": 2.9, "onset_rate": 3.4, "dynamic_span": 5.8}
    calm = {"loudness": 0.09, "low_end": 0.9, "onset_rate": 0.9, "dynamic_span": 2.0}

    app.session_state["favorites"] = {
        f"calm artist {i}|piano": {
            "artist": f"Calm Artist {i}", "track": "Piano Cover",
            "genre": "Classical", "year": "2019", "features": dict(calm),
            "added_at": 1_700_000_000.0,
        }
        for i in range(6)
    }
    app.session_state["candidates"] = [
        track("Loud Band", "Clocks (Epic Trailer Version)", "loud", genre="Soundtrack"),
        track("Quiet Pianist", "Clocks (Solo Piano)", "calm", genre="Classical"),
    ]
    app.session_state["bigness"] = {"itunes-loud": loud, "itunes-calm": calm}
    app.run()

    assert not app.exception
    order = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert order.index("btn_favorite_itunes-calm") < order.index("btn_favorite_itunes-loud")

    # ובלי הלמידה, אותם נתונים בדיוק נותנים את הסדר ההפוך — אבל רק אחרי
    # "סדר מחדש": הסדר קפוא בזמן עיון כדי שהרשימה לא תזוז תוך כדי האזנה
    app.session_state["favorites"] = {}
    app.run()
    frozen = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert frozen.index("btn_favorite_itunes-calm") < frozen.index("btn_favorite_itunes-loud")

    [b for b in app.button if (b.label or "").startswith("Re-sort")][0].click().run()
    order = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert order.index("btn_favorite_itunes-loud") < order.index("btn_favorite_itunes-calm")


def test_without_favorites_the_default_sort_falls_back_to_measured_size(app):
    big = {"loudness": 0.30, "low_end": 3.0, "onset_rate": 3.5, "dynamic_span": 6.0}
    small = {"loudness": 0.08, "low_end": 0.8, "onset_rate": 0.8, "dynamic_span": 1.5}
    app.session_state["candidates"] = [
        track("Quiet", "A", "small"),
        track("Loud", "B", "big"),
    ]
    app.session_state["bigness"] = {"itunes-small": small, "itunes-big": big}
    app.run()

    assert not app.exception
    order = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert order.index("btn_favorite_itunes-big") < order.index("btn_favorite_itunes-small")


def test_thumbs_down_pushes_that_style_down(app):
    """דחייה היא לא הסתרה: הטראק נשאר, אבל יורד — וגם דומים לו."""
    loud = {"loudness": 0.29, "low_end": 2.9, "onset_rate": 3.4, "dynamic_span": 5.8}
    calm = {"loudness": 0.09, "low_end": 0.9, "onset_rate": 0.9, "dynamic_span": 2.0}

    app.session_state["favorites"] = {
        f"calm {i}|x": {"artist": f"Calm {i}", "track": "X", "genre": "Classical",
                        "year": "2019", "features": dict(calm), "added_at": 1.0}
        for i in range(4)
    }
    app.session_state["rejections"] = {
        f"loud {i}|y": {"artist": f"Loud {i}", "track": "Y", "genre": "Soundtrack",
                        "year": "2019", "features": dict(loud), "added_at": 1.0}
        for i in range(4)
    }
    app.session_state["candidates"] = [
        track("New Loud", "Clocks (Epic)", "loud", genre="Soundtrack"),
        track("New Calm", "Clocks (Piano)", "calm", genre="Classical"),
    ]
    app.session_state["bigness"] = {"itunes-loud": loud, "itunes-calm": calm}
    app.run()

    assert not app.exception
    keys = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert keys.index("btn_favorite_itunes-calm") < keys.index("btn_favorite_itunes-loud")
    # הדחוי עדיין מוצג, רק נמוך
    assert "btn_favorite_itunes-loud" in keys


def test_thumbs_down_button_saves_and_clears_the_heart(app):
    app.session_state["candidates"] = [track("2WEI", "Zombie (Epic)", "e1")]
    app.run()

    app.button(key="btn_favorite_itunes-e1").click().run()
    assert len(app.session_state["favorites"]) == 1

    app.button(key="btn_reject_itunes-e1").click().run()

    assert not app.exception
    # אותו טראק לא יכול להיות גם אהוב וגם דחוי
    assert app.session_state["favorites"] == {}
    assert len(app.session_state["rejections"]) == 1
    assert storage.load_rejections()


def test_switching_classics_category_changes_the_songs(app):
    import classics
    labels = list(classics.CATEGORIES)

    _nav(app, "Charts")
    picker = app.selectbox(key="classics_category")
    assert picker.options == labels

    picker.set_value("50's").run()
    assert not app.exception
    fifties = {b.label for b in app.button if (b.key or "").startswith("classic_")}

    picker.set_value("2000's").run()
    assert not app.exception
    two_thousands = {b.label for b in app.button if (b.key or "").startswith("classic_")}

    assert fifties and two_thousands
    assert not (fifties & two_thousands)


def test_blues_category_is_reachable(app):
    _nav(app, "Charts")
    picker = app.selectbox(key="classics_category")
    picker.set_value("Blues").run()

    assert not app.exception
    labels = " ".join(b.label for b in app.button if (b.key or "").startswith("classic_"))
    assert "Muddy Waters" in labels


def test_every_category_renders_without_a_repeating_artist(app):
    """התלונה: "שירים לא מוכרים וחוזרים על עצמם" — התקרה חייבת להחזיק בממשק."""
    import collections

    import classics

    _nav(app, "Charts")
    picker = app.selectbox(key="classics_category")
    for label in classics.CATEGORIES:
        picker.set_value(label).run()
        assert not app.exception, label

        buttons = [b for b in app.button if (b.key or "").startswith("classic_")]
        assert buttons, f"קטגוריה ריקה בממשק: {label}"

        artists = collections.Counter(
            (b.help or b.label).split(" — ")[-1] for b in buttons)
        assert artists.most_common(1)[0][1] <= 2, f"{label}: {artists.most_common(1)}"


def test_a_saved_version_is_clickable_and_searches_for_it_again(app, monkeypatch):
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track("Someone", f"{title} (Cover)", "c1")], "src", None))
    app.session_state["favorites"] = {
        "2wei|zombie": {"artist": "2WEI", "track": "Zombie", "genre": "Soundtrack",
                        "year": "2018", "features": None, "added_at": 1.0}
    }
    _nav(app, "Loved")

    app.button(key="fav_open_2wei|zombie").click().run()

    assert not app.exception
    assert app.session_state["cover_title"] == "Zombie"
    assert app.session_state["cover_artist"] == "2WEI"
    assert app.session_state["search_mode"] == "Covers of a song"
    assert app.session_state["candidates"]


def test_a_saved_artist_ranks_their_other_covers_higher(app):
    """הבקשה: קאבר של אמן ששמור עולה, גם כשזה קאבר לשיר אחר."""
    app.session_state["favorites"] = {
        f"violet orlandi|song {i}": {
            "artist": "Violet Orlandi", "track": f"Song {i}", "genre": "Rock",
            "year": "2019", "features": None, "added_at": 1.0}
        for i in range(4)
    }
    app.session_state["candidates"] = [
        track("Unknown Cover Band", "Clocks (Cover)", "unknown", genre="Rock"),
        track("Violet Orlandi", "Clocks (Cover)", "known", genre="Rock"),
    ]
    app.run()

    assert not app.exception
    keys = [b.key for b in app.button if (b.key or "").startswith("btn_favorite_")]
    assert keys.index("btn_favorite_itunes-known") < keys.index("btn_favorite_itunes-unknown")


# ---------- "Wrong category?" ----------

def _soundtrack(uid="cat1", title="Lollipop"):
    return track("Ronnie Minder", title, uid,
                 album="Kane (Original Motion Picture Soundtrack)")


def test_a_wrong_category_can_be_corrected_from_the_row(app):
    """הבקשה: כפתור בשורה שנותן את האופציות, והתיקון נלמד."""
    import buckets

    app.session_state["candidates"] = [_soundtrack()]
    app.run()
    assert not app.exception

    picker = [s for s in app.selectbox if s.key == "cat_itunes-cat1"]
    assert picker, "אין בורר קטגוריה בשורה"
    assert list(picker[0].options) == list(buckets.ORDER)
    # שם האלבום לבדו הוא מה שמסווג את השורה כטריילר
    assert picker[0].value == buckets.TRAILER

    picker[0].set_value(buckets.OTHER).run()
    assert not app.exception
    assert storage.load_category_corrections(), "התיקון לא נשמר בכלל"


def test_the_correction_is_shared_and_survives_a_new_search(app):
    """דיווח אחד מציל את כל מי שיראה את אותה גרסה אחריו — כולל חיפוש אחר
    לגמרי, שבו היא חוזרת עם uid אחר."""
    import buckets

    app.session_state["candidates"] = [_soundtrack()]
    app.run()
    [s for s in app.selectbox if s.key == "cat_itunes-cat1"][0].set_value(
        buckets.OTHER).run()

    # אותה גרסה, חיפוש אחר, מזהה חנות אחר
    app.session_state["candidates"] = [_soundtrack(uid="from-another-search")]
    app.run()

    assert not app.exception
    again = [s for s in app.selectbox if s.key == "cat_itunes-from-another-search"]
    assert again and again[0].value == buckets.OTHER


def test_the_filter_buttons_agree_with_the_correction(app):
    """בלי זה השורה זזה בתפריט אבל לא בכפתורי הסינון שמעל התוצאות."""
    import buckets

    app.session_state["candidates"] = [
        _soundtrack(), track("Somebody", "Yellow (Rock Cover)", "rock1")]
    app.run()

    def kinds():
        row = [p for p in app.pills if p.key == "bucket_filter"]
        assert row, "שורת הקטגוריות נעלמה"
        # התוויות נושאות מונה ("Trailer / epic (1)")
        return {label.rsplit(" (", 1)[0] for label in row[0].options}

    assert buckets.TRAILER in kinds()

    [s for s in app.selectbox if s.key == "cat_itunes-cat1"][0].set_value(
        buckets.OTHER).run()

    assert not app.exception
    assert buckets.TRAILER not in kinds(), "הקטגוריה הישנה עדיין נספרת"
