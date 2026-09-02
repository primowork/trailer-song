"""מעקף ה-CORS: השרת מושך את הבייטים. אין רשת בטסטים."""
import base64

import httpx
import pytest

import preview


REAL_CLIENT = httpx.Client   # נתפס לפני ה-patch, אחרת המפעל קורא לעצמו


def _client(handler):
    """httpx.Client שמדבר מול transport מזויף, בלי לצאת לרשת."""
    def make(**kwargs):
        kwargs.pop("transport", None)
        return REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs)
    return make


@pytest.fixture
def serve(monkeypatch):
    def install(handler):
        monkeypatch.setattr(preview.httpx, "Client", _client(handler))
    return install


def test_bytes_become_a_data_uri(serve):
    serve(lambda request: httpx.Response(
        200, content=b"ID3audio", headers={"content-type": "audio/mp4; codecs=mp4a"}))
    data_uri, error = preview.fetch_data_uri("http://store/preview.m4a")
    assert not error
    assert data_uri.startswith("data:audio/mp4;base64,")
    assert base64.b64decode(data_uri.split(",", 1)[1]) == b"ID3audio"


def test_non_audio_content_type_falls_back(serve):
    serve(lambda request: httpx.Response(200, content=b"x",
                                         headers={"content-type": "text/html"}))
    data_uri, error = preview.fetch_data_uri("http://store/preview.m4a")
    assert not error and data_uri.startswith(f"data:{preview.DEFAULT_TYPE};base64,")


def test_blocked_server_reports_the_reason(serve):
    def boom(request):
        raise httpx.ConnectTimeout("timed out")
    serve(boom)
    data_uri, error = preview.fetch_data_uri("http://store/preview.m4a")
    assert not data_uri and "השרת" in error


def test_http_error_is_an_error_not_empty_audio(serve):
    serve(lambda request: httpx.Response(403, content=b""))
    data_uri, error = preview.fetch_data_uri("http://store/preview.m4a")
    assert not data_uri and error


def test_empty_and_oversized_are_rejected(serve):
    serve(lambda request: httpx.Response(200, content=b""))
    assert preview.fetch_data_uri("http://store/p")[1] == "קובץ ריק"

    serve(lambda request: httpx.Response(200, content=b"x" * (preview.MAX_BYTES + 1)))
    assert "גדול מדי" in preview.fetch_data_uri("http://store/p")[1]


def test_missing_url_is_not_a_network_call():
    assert preview.fetch_data_uri("") == ("", "אין preview")
