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


def test_classics_is_the_default_index_source_and_needs_no_network(app):
    # אין כאן שום monkeypatch לרשת — קלאסיקות היא רשימה סטטית
    assert app.radio(key="index_source").value.startswith("🎻 קלאסיקות")
    assert any((b.key or "").startswith("classic_") for b in app.button)


def test_classics_song_click_runs_a_focused_song_search(app, monkeypatch):
    import classics
    first = classics.POP_CLASSICS[0]
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
    first = artists.GREATEST_ARTISTS[0]
    app.button(key=f"goat_0_{first[:30]}").click().run()

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
    first = artists.GREATEST_ARTISTS[0]
    app.button(key=f"goat_0_{first[:30]}").click().run()

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
    app.button(key="imp_hot-100_0_Umbrella").click().run()

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
