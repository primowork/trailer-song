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
import search as search_module

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def track(artist, title, uid, **extra):
    return {"source": "iTunes", "uid": f"itunes-{uid}", "artist": artist,
            "track": title, "album": "", "duration_sec": 200,
            "preview_url": "http://p", "artwork": "", "genre": "",
            "release_date": "", "year": "2020", "score": 50, **extra}


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


def test_the_page_renders(app):
    assert not app.exception


def test_greatest_artist_click_fills_the_field_and_searches(app, monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yesterday"])
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=12: ([track("Epic", f"{title} (Epic)", "e1")], "src"))

    app.button(key="goat_1").click().run()

    assert not app.exception
    assert app.session_state["cover_artist"] == artists.GREATEST_ARTISTS[0]
    assert app.session_state["candidates"]
    assert app.session_state["candidates"][0]["origin_track"] == "Yesterday"


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
                        lambda title, artist="", limit=40: ([track("Other", f"{title} (Cinematic)", "o1")], "src"))
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
