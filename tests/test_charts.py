"""מצעדי Deezer. אין רשת: get_json ממוקם."""
import charts


TRACK_PAYLOAD = {"data": [
    {"id": 1, "title": "Umbrella", "duration": 260, "preview": "http://p",
     "artist": {"name": "Rihanna"}, "album": {"title": "Good Girl Gone Bad",
                                              "cover_medium": "http://c"}},
]}


def test_chart_tracks_come_back_as_normal_tracks(monkeypatch, tmp_path):
    monkeypatch.setattr(charts.storage, "DATA_DIR", str(tmp_path))
    charts._cache = {}
    monkeypatch.setattr(charts, "get_json", lambda url, **kwargs: TRACK_PAYLOAD)

    tracks = charts.chart_tracks()
    assert tracks[0]["artist"] == "Rihanna" and tracks[0]["track"] == "Umbrella"
    assert tracks[0]["uid"].startswith("deezer-")
    assert tracks[0]["preview_url"] == "http://p"


def test_a_failed_chart_is_empty_and_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(charts.storage, "DATA_DIR", str(tmp_path))
    charts._cache = {}
    monkeypatch.setattr(charts, "get_json", lambda url, **kwargs: None)

    assert charts.chart_tracks() == []
    # הכישלון נשמר בזיכרון לזמן קצר בלבד, ולא נכתב לדיסק כאילו היה מצעד
    entry = list(charts._cache.values())[0]
    assert not entry["value"]
    assert not (tmp_path / charts.CACHE_FILE).exists()


def test_a_failure_is_retried_after_its_short_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(charts.storage, "DATA_DIR", str(tmp_path))
    charts._cache = {}
    calls = []

    def fake(url, **kwargs):
        calls.append(url)
        return None

    monkeypatch.setattr(charts, "get_json", fake)
    charts.chart_tracks()
    charts.chart_tracks()
    assert len(calls) == 1              # לא מנסים שוב בכל rerun

    for entry in charts._cache.values():
        entry["at"] -= charts.FAILURE_TTL + 1
    charts.chart_tracks()
    assert len(calls) == 2              # אבל כן אחרי שהתוקף הקצר עבר


def test_the_second_call_is_served_from_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(charts.storage, "DATA_DIR", str(tmp_path))
    charts._cache = {}
    calls = []

    def fake(url, **kwargs):
        calls.append(url)
        return TRACK_PAYLOAD

    monkeypatch.setattr(charts, "get_json", fake)
    charts.chart_tracks()
    charts.chart_tracks()
    assert len(calls) == 1


def test_genres_and_artists_are_flattened(monkeypatch, tmp_path):
    monkeypatch.setattr(charts.storage, "DATA_DIR", str(tmp_path))
    charts._cache = {}
    payloads = {
        charts.DEEZER_GENRE: {"data": [{"id": 0, "name": "All"}, {"id": 132, "name": "Pop"},
                                       {"name": "בלי id"}]},
        f"{charts.DEEZER_CHART}/0/artists": {"data": [{"name": "Drake"}, {"nope": 1}]},
    }
    monkeypatch.setattr(charts, "get_json", lambda url, **kwargs: payloads.get(url))

    assert charts.genres() == [{"id": 0, "name": "All"}, {"id": 132, "name": "Pop"}]
    assert charts.chart_artists() == ["Drake"]
