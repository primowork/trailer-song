"""שכבת האישור: האם השיר באמת שימש בטריילר."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import youtube


def test_actual_trailer_use_is_recognized():
    for text in [
        "2WEI - Survivor (Official Trailer Music)",
        "Sia - California Dreamin' from the San Andreas trailer",
        "Zombie — as heard in the Wonder Woman trailer",
        "Paint It Black | Official Trailer | Netflix",
    ]:
        assert youtube.looks_like_trailer_use(text), text


def test_epic_styling_alone_is_not_evidence():
    """ההבחנה שכל הגישה הקודמת פספסה: 'אפי' אינו 'שימש בטריילר'."""
    for text in [
        "Epic orchestral cover of Zombie",
        "Cinematic version - dark piano cover",
        "Patsy Cline - Sweet Dreams (Official Audio)",
        "Hits Covered By Snow - full album",
    ]:
        assert not youtube.looks_like_trailer_use(text), text


def test_no_api_key_returns_nothing_quietly(monkeypatch):
    monkeypatch.setattr(youtube, "API_KEY", "")
    assert youtube.search_trailer_evidence("Sia", "California Dreamin'") == []
    assert youtube.available() is False


def test_evidence_is_filtered_to_trailer_mentions(monkeypatch):
    monkeypatch.setattr(youtube, "API_KEY", "test-key")
    monkeypatch.setattr(youtube, "_cache", {})
    monkeypatch.setattr(youtube.storage, "_save_json", lambda *a, **k: True)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"items": [
                {"id": {"videoId": "aaa"}, "snippet": {
                    "title": "Sia - California Dreamin' (Official Trailer Music)",
                    "channelTitle": "TrailerTunes", "description": ""}},
                {"id": {"videoId": "bbb"}, "snippet": {
                    "title": "Sia - California Dreamin' (Lyrics)",
                    "channelTitle": "LyricsChannel", "description": ""}},
            ]}

    class FakeClient:
        def get(self, *a, **k):
            return FakeResponse()

    evidence = youtube.search_trailer_evidence("Sia", "California Dreamin'",
                                               client=FakeClient())
    assert [e["video_id"] for e in evidence] == ["aaa"]
    assert evidence[0]["url"].endswith("aaa")
    assert evidence[0]["channel"] == "TrailerTunes"


def test_api_error_returns_nothing(monkeypatch):
    monkeypatch.setattr(youtube, "API_KEY", "test-key")
    monkeypatch.setattr(youtube, "_cache", {})

    class Failing:
        def get(self, *a, **k):
            raise RuntimeError("quota exceeded")

    assert youtube.search_trailer_evidence("A", "B", client=Failing()) == []


def test_results_are_cached_to_respect_the_quota(monkeypatch):
    """100 חיפושים ביום במכסת ברירת המחדל — קאש הוא חובה, לא אופציה."""
    monkeypatch.setattr(youtube, "API_KEY", "test-key")
    monkeypatch.setattr(youtube, "_cache", {})
    monkeypatch.setattr(youtube.storage, "_save_json", lambda *a, **k: True)
    calls = []

    class CountingClient:
        def get(self, *a, **k):
            calls.append(1)

            class R:
                status_code = 200
                def json(self):
                    return {"items": []}
            return R()

    client = CountingClient()
    youtube.search_trailer_evidence("Sia", "X", client=client)
    youtube.search_trailer_evidence("Sia", "X", client=client)
    assert len(calls) == 1
