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

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def track(artist, title, uid, **extra):
    return {"source": "iTunes", "uid": f"itunes-{uid}", "artist": artist,
            "track": title, "album": "", "duration_sec": 200,
            "preview_url": "http://p", "artwork": "", "genre": "",
            "release_date": "", "year": "2020", "score": 50, **extra}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """מבודד כל טסט מהדיסק המשותף — בלי זה טסטים חולקים קאש/רשימה שחורה בין ריצות."""
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


def test_the_page_renders(app):
    assert not app.exception


def _page_css(app) -> str:
    return " ".join(m.value for m in app.markdown if "<style>" in (m.value or ""))


def test_the_root_stays_ltr_below_the_mobile_breakpoint(app):
    """`direction: rtl` על השורש שבר את קיפול הסרגל בטלפון.

    Streamlit מסתיר את הסרגל בנייד עם `translateX` שלילי. כיווניות הפוכה על
    `stAppViewContainer` הפכה את ההזזה: הסרגל נשאר על המסך, נמעך לכ-50px,
    וחפף לתוכן — האפליקציה הייתה בלתי שמישה בטלפון. הכיווניות על השורש
    חייבת להישאר מאחורי media query של דסקטופ.
    """
    css = _page_css(app)
    assert '[data-testid="stMain"] { direction: rtl; }' in css

    before_root_rule = css.split('[data-testid="stAppViewContainer"]')[0]
    assert "@media (min-width: 768px)" in before_root_rule


def test_the_content_column_is_capped_so_it_does_not_stretch(app):
    """ב-layout="wide" הטופס נמתח על פני 1400px ומפזר את העין."""
    assert "max-width: 1180px" in _page_css(app)


def test_classics_is_the_default_index_source_and_needs_no_network(app):
    # אין כאן שום monkeypatch לרשת — קלאסיקות היא רשימה סטטית
    assert app.radio(key="index_source").value.startswith("🎻 קלאסיקות")
    assert any((b.key or "").startswith("classic_") for b in app.button)


def test_classics_song_click_runs_a_focused_song_search(app, monkeypatch):
    import classics
    # הקטגוריה הראשונה היא ברירת המחדל של ה-selectbox
    first = classics.CATEGORIES[next(iter(classics.CATEGORIES))][0]
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track(first["artist"], f"{title} (Cover)", "c1")], "src", None))

    classics_button = [b for b in app.button if (b.key or "").startswith("classic_")][0]
    classics_button.click().run()

    assert not app.exception
    assert app.session_state["search_mode"] == "🎬 קאברים לשיר"
    assert app.session_state["cover_title"] == first["track"]
    assert app.session_state["cover_artist"] == first["artist"]
    assert app.session_state["candidates"]


def test_greatest_artist_click_shows_a_preview_before_searching(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=12, filters=None, prefer_new=False, min_year=0:
                            ([track("Epic", f"{title} (Epic)", "e1")], "src"))

    # האינדקס נפתח על המצעד החי; רשימת בילבורד היא המקור השני
    source = app.radio(key="index_source")
    source.set_value(source.options[1]).run()
    app.button(key="goat_0").click().run()

    assert not app.exception
    assert app.session_state["cover_artist"] == artists.GREATEST_ARTISTS[0]
    assert app.session_state["search_mode"] == "🎤 קאברים לאמן"
    # לא הורץ חיפוש קאברים יקר מיד — קודם מוצגת תצוגה מקדימה זולה
    assert app.session_state["candidates"] == []
    assert any("Yesterday" in b.label for b in app.button
              if (b.key or "").startswith("artist_preview_"))

    # "🔎 חפש" מריץ את החיפוש המלא לפי האמן, בדיוק כמו היום
    search_button = [b for b in app.button if b.label == "🔎 חפש"][0]
    search_button.click().run()

    assert not app.exception
    assert app.session_state["candidates"]
    assert app.session_state["candidates"][0]["origin_track"] == "Yesterday"


def test_artist_preview_song_click_runs_a_focused_song_search(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda title, artist="", **k: (
                            [track("Beatles", f"{title} (Cover)", "c1")], "src", None))

    source = app.radio(key="index_source")
    source.set_value(source.options[1]).run()
    app.button(key="goat_0").click().run()

    preview_button = [b for b in app.button
                     if (b.key or "").startswith("artist_preview_")][0]
    preview_button.click().run()

    assert not app.exception
    assert app.session_state["search_mode"] == "🎬 קאברים לשיר"
    assert app.session_state["cover_title"] == "Yesterday"
    assert app.session_state["candidates"]
    assert app.session_state["candidates"][0]["uid"] == "itunes-c1"


def test_suggestion_click_fills_both_fields(app, monkeypatch):
    catalog = [track("The Verve", "Bitter Sweet Symphony", "v1")]
    monkeypatch.setattr(search_module, "itunes_search", lambda *a, **k: [dict(c) for c in catalog])

    app.session_state["cover_title"] = "bitter sweet symphany"
    app.run()
    app.button(key="sug_0").click().run()

    assert not app.exception
    assert app.session_state["cover_title"] == "Bitter Sweet Symphony"
    assert app.session_state["cover_artist"] == "The Verve"


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


def test_measured_row_shows_the_score_and_the_raw_numbers(app):
    app.session_state["candidates"] = [track("Epic Covers", "Yellow (Epic)", "e1")]
    app.session_state["bigness"] = {"itunes-e1": {"loudness": 0.30, "low_end": 3.0,
                                                 "onset_rate": 4.0, "dynamic_span": 6.0}}
    app.run()

    assert not app.exception
    captions = [c.value for c in app.caption]
    assert any("🔊 גדול" in text and "עוצמה" in text for text in captions)
    assert any("ייצא מדדים" in b.label for b in app.get("download_button"))


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
    source = app.radio(key="index_source")
    source.set_value(source.options[-1]).run()
    app.button(key="imp_hot-100_0").click().run()

    assert not app.exception
    assert app.session_state["cover_title"] == "Umbrella"
    assert app.session_state["cover_artist"] == "Rihanna"
    assert app.session_state["search_mode"] == "🎬 קאברים לשיר"
    assert app.session_state["candidates"]


def test_search_mode_radio_has_three_options(app):
    modes = app.radio(key="search_mode")
    assert modes.options == ["🎬 קאברים לשיר", "🎤 קאברים לאמן", "🔎 חיפוש חופשי + פילטרים"]


def test_song_mode_dispatches_to_find_all_covers(app, monkeypatch):
    called = {}
    monkeypatch.setattr(covers, "find_all_covers",
                        lambda *a, **k: (called.setdefault("hit", True) and
                                        [track("X", "Y", "y1")], "src", None))
    app.text_input(key="cover_title").set_value("Yellow").run()
    search_button = [b for b in app.button if b.label == "🔎 חפש"][0]
    search_button.click().run()

    assert not app.exception
    assert called.get("hit")
    assert app.session_state["candidates"][0]["uid"] == "itunes-y1"


def test_artist_mode_dispatches_to_find_artist_covers(app, monkeypatch):
    called = {}
    monkeypatch.setattr(covers, "find_artist_covers",
                        lambda *a, **k: (called.setdefault("hit", True) and
                                        [track("X", "Y", "y2")], "src", ["Y"]))
    modes = app.radio(key="search_mode")
    modes.set_value("🎤 קאברים לאמן").run()
    app.text_input(key="cover_artist").set_value("Coldplay").run()
    search_button = [b for b in app.button if b.label == "🔎 חפש"][0]
    search_button.click().run()

    assert not app.exception
    assert called.get("hit")
    assert app.session_state["candidates"][0]["uid"] == "itunes-y2"


def test_free_mode_dispatches_to_search_covers(app, monkeypatch):
    called = {}
    monkeypatch.setattr(search_module, "search_covers",
                        lambda *a, **k: called.setdefault("hit", True) and
                                        [track("X", "Y", "y3")])
    modes = app.radio(key="search_mode")
    modes.set_value("🔎 חיפוש חופשי + פילטרים").run()
    app.text_input(key="cover_title").set_value("Yellow").run()
    search_button = [b for b in app.button if b.label == "🔎 חפש"][0]
    search_button.click().run()

    assert not app.exception
    assert called.get("hit")
    assert app.session_state["candidates"][0]["uid"] == "itunes-y3"


def test_filters_thread_through_to_song_mode(app, monkeypatch):
    """לפני האיחוד רק החיפוש החופשי כיבד את הפילטרים; עכשיו כולם."""
    seen = {}

    def fake(title, artist="", filters=None, prefer_new=False, min_year=0, work_id="", limit=80):
        seen["filters"] = filters
        return [], "", None

    monkeypatch.setattr(covers, "find_all_covers", fake)
    app.text_input(key="cover_title").set_value("Yellow").run()
    search_button = [b for b in app.button if b.label == "🔎 חפש"][0]
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


def test_the_playlist_replaces_the_blacklist_in_the_sidebar(app):
    headers = [m.value for m in app.markdown]
    assert any("❤️ הפלייליסט שלי" in text for text in headers)
    # החסימה עדיין קיימת — רק ירדה לאקספנדר מכווץ
    assert not any("### 🚫 אמנים ברשימה השחורה" in text for text in headers)


# ---------- יציבות הסדר ----------

BIG = {"loudness": 0.30, "low_end": 3.0, "onset_rate": 3.5, "dynamic_span": 6.0}
SMALL = {"loudness": 0.08, "low_end": 0.8, "onset_rate": 0.8, "dynamic_span": 1.5}


def _row_order(app) -> list:
    return [(b.key or "").replace("btn_favorite_", "")
            for b in app.button if (b.key or "").startswith("btn_favorite_")]


def _thirty(genre_of=lambda i: "Soundtrack"):
    return [track(f"A{i}", f"T{i}", f"u{i}", score=100 - i, genre=genre_of(i))
            for i in range(30)]


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

    picker = [s for s in app.selectbox if s.label == "מיון:"][0]
    picker.set_value("אמן").run()

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
    [b for b in app.button if b.label == "🔎 חפש"][0].click().run()

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


def test_the_resort_control_never_appears_or_disappears(app):
    """כפתור שצץ מעל הרשימה דוחף את כל מה שמתחתיו — וזה מזיז את המקום.

    לכן הוא מצויר תמיד, ומושבת כשאין מה לסדר.
    """
    app.session_state["candidates"] = _thirty()
    app.run()
    quiet = [b for b in app.button if (b.label or "").startswith("🔄")]
    assert len(quiet) == 1 and quiet[0].disabled

    app.session_state["bigness"] = {f"itunes-u{i}": (BIG if i in (5, 17, 19) else SMALL)
                                    for i in range(20)}
    app.run()
    active = [b for b in app.button if (b.label or "").startswith("🔄")]
    assert len(active) == 1 and not active[0].disabled
    assert "יזוזו" in active[0].label


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

    [b for b in app.button if (b.label or "").startswith("🔄 סדר מחדש")][0].click().run()
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
    picker = app.selectbox(key="classics_category")
    picker.set_value("🎺 בלוז").run()

    assert not app.exception
    labels = " ".join(b.label for b in app.button if (b.key or "").startswith("classic_"))
    assert "Muddy Waters" in labels


def test_every_category_renders_without_a_repeating_artist(app):
    """התלונה: "שירים לא מוכרים וחוזרים על עצמם" — התקרה חייבת להחזיק בממשק."""
    import collections

    import classics

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
    app.run()

    app.button(key="fav_open_2wei|zombie").click().run()

    assert not app.exception
    assert app.session_state["cover_title"] == "Zombie"
    assert app.session_state["cover_artist"] == "2WEI"
    assert app.session_state["search_mode"] == "🎬 קאברים לשיר"
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
