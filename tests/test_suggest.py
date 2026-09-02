"""ההשלמה והתיקון נבדקים מול קטלוג מזויף: אין רשת בטסטים."""
import pytest

import search as search_module
import suggest


CATALOG = [
    {"track": "Bitter Sweet Symphony", "artist": "The Verve", "year": "1997"},
    {"track": "Bitter Sweet Symphony (Live)", "artist": "The Verve", "year": "2004"},
    {"track": "Sweet Child O' Mine", "artist": "Guns N' Roses", "year": "1987"},
]


@pytest.fixture
def catalog(monkeypatch):
    calls = []

    def fake_search(term, limit=25, **kwargs):
        calls.append(term)
        return [dict(item) for item in CATALOG]

    monkeypatch.setattr(search_module, "itunes_search", fake_search)
    return calls


def test_layout_swap_is_exact():
    # "winter" שהוקלד כשהמקלדת בעברית
    assert suggest.fix_layout("'ןמאקר") == "winter"
    assert suggest.fix_layout("דטצפיםמט") == "symphony"
    # טקסט אנגלי אינו משתנה
    assert suggest.fix_layout("symphony") == "symphony"


def test_hebrew_detection():
    assert suggest.has_hebrew("שיר")
    assert not suggest.has_hebrew("song 2")


def test_partial_name_completes(catalog):
    items = suggest.suggest("bitter sweet symph")
    assert items[0]["track"] == "Bitter Sweet Symphony"
    assert items[0]["artist"] == "The Verve"


def test_misspelling_is_offered_as_a_correction(catalog):
    correction = suggest.did_you_mean("bitter sweet symphany")
    assert correction and correction["track"] == "Bitter Sweet Symphony"


def test_correct_input_gets_no_correction(catalog):
    assert suggest.did_you_mean("Bitter Sweet Symphony") is None


def test_unrelated_input_gets_no_correction(catalog):
    # "אולי התכוונת" על שיר אחר לגמרי הוא רעש, לא עזרה
    assert suggest.did_you_mean("zzzz qqqq wwww") is None


def test_short_input_is_ignored(catalog):
    assert suggest.suggest("ab") == []
    assert suggest.did_you_mean("ab") is None
    assert catalog == []


def test_hebrew_layout_input_also_queries_the_swapped_term(catalog):
    suggest.suggest("דטצפיםמט")
    assert "symphony" in catalog


def test_suggestions_are_deduped_and_capped(catalog):
    items = suggest.suggest("bitter sweet symphony", limit=2)
    assert len(items) == 2
    labels = [item["label"] for item in items]
    assert len(set(labels)) == 2
