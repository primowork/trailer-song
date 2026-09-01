"""רגרסיה על מקרה הבוחן: Sia - California Dreamin' (טריילר San Andreas).

זמרת מוכרת, שיר ישן, טריילר — הארכיטיפ הנפוץ ביותר, והמערכת פספסה אותו מארבע
סיבות נפרדות. כל טסט כאן נועל אחת מהן.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import covers
import search

TYPED = "California Dreaming"           # מה שהמשתמש מקליד
REAL = "California Dreamin'"            # השם האמיתי
ITUNES_PARENS = 'California Dreamin\' (From "San Andreas")'
ITUNES_DASH = 'California Dreamin\' - From "San Andreas"'


def make(artist, track, album="", genre="", preview="http://p"):
    return {
        "source": "iTunes", "uid": "x", "artist": artist, "track": track, "album": album,
        "duration_sec": 200, "preview_url": preview, "artwork": "", "genre": genre,
    }


SIA = make("Sia", REAL, "San Andreas Soundtrack", "Pop")
SPAM = make("Nobody Ever", "California Dreaming (Epic Cinematic Trailer Cover Version)",
            "Epic Trailer Covers Vol 3", "Pop")


# ---------- (1) האפוסטרוף ----------

def test_typed_title_and_real_title_share_one_key():
    assert search.track_key("Sia", TYPED) == search.track_key("Sia", REAL)


def test_all_four_title_variants_collapse_to_one_key():
    keys = {search.track_key("Sia", v) for v in (TYPED, REAL, ITUNES_PARENS, ITUNES_DASH)}
    assert len(keys) == 1


def test_normalization_does_not_mangle_innocent_titles():
    """מוסיף g רק אחרי אפוסטרוף, לעולם לא מוריד g קיים."""
    for title in ("Sing", "Bring Me To Life", "Coming From Nowhere", "Everything"):
        assert search.normalize_title(title) == title.lower()


def test_apostrophe_forms_normalize_to_the_g_form():
    assert search.normalize_title("Nothin' but a Good Time") == "nothing but a good time"
    assert search.normalize_title("Knockin' on Heaven's Door") == "knocking on heavens door"


# ---------- (2) הדירוג ----------

def test_real_cover_outranks_keyword_spam():
    """הרגרסיה: קודם Sia קיבלה 97 והזבל 140."""
    assert search.score_track(SIA, TYPED) > search.score_track(SPAM, TYPED)


def test_epic_bonus_is_capped():
    stuffed = make("2WEI", "Epic Trailer Cinematic Cover Version",
                   "Epic Orchestral Trailer Score", "Soundtrack")
    assert search.epic_bonus(stuffed) <= search.MAX_EPIC_BONUS


def test_relevance_dominates_over_epic_bonus():
    """התאמה מדויקת ללא סימני אפיות מנצחת אי-התאמה עם כל הסימנים."""
    exact = make("Someone", TYPED)
    irrelevant = make("2WEI", "Totally Different Song", "Epic Trailer Cover", "Soundtrack")
    assert search.score_track(exact, TYPED) > search.score_track(irrelevant, TYPED)


# ---------- (3) סימן הטריילר ----------

# ---------- (4) ההעשרה ----------

def test_enrichment_matches_the_store_title_variant(monkeypatch):
    """'California Dreamin\\' - From "San Andreas"' חייב להתאים ולהחזיר preview."""
    store_hit = make("Sia", ITUNES_DASH, "San Andreas", "Pop")
    monkeypatch.setattr(covers.search_module, "itunes_search", lambda *a, **k: [store_hit])
    version = {"artist": "Sia", "track": REAL, "source_db": "SecondHandSongs"}
    enriched = covers._enrich_one(version, None)
    assert enriched["preview_url"] == "http://p"


def test_enrichment_rejects_a_different_song(monkeypatch):
    wrong = make("Sia", "Chandelier")
    monkeypatch.setattr(covers.search_module, "itunes_search", lambda *a, **k: [wrong])
    monkeypatch.setattr(covers.search_module, "deezer_search", lambda *a, **k: [])
    version = {"artist": "Sia", "track": REAL, "source_db": "SecondHandSongs"}
    enriched = covers._enrich_one(version, None)
    assert enriched["preview_url"] == ""  # לא מתאים -> נפילה לאחור, לא התאמה שגויה
