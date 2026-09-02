"""הפרסר של עמודי בילבורד. הפיקסטורות משקפות את המבנה בעמוד אמיתי."""
import billboard

ROW = """
<div class="o-chart-results-list-row-container">
  <ul class="o-chart-results-list-row">
    <li class="o-chart-results-list__item"><span class="c-label">{rank}</span></li>
    <li class="o-chart-results-list__item">
      <h3 id="title-of-a-story" class="c-title">{primary}</h3>
      <span class="c-label">{secondary}</span>
      <span class="c-label">{rank}</span>
      <span class="c-label">1/1/2021</span>
    </li>
  </ul>
</div>
"""


def page(title, rows):
    body = "".join(ROW.format(**row) for row in rows)
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def test_songs_chart_keeps_title_and_artist():
    html = page("Hot 100", [
        {"rank": 1, "primary": "Umbrella", "secondary": "Rihanna Featuring Jay-Z"},
        {"rank": 2, "primary": "Yellow", "secondary": "Coldplay"},
    ])
    chart = billboard.parse_chart(html)
    assert chart["title"] == "Hot 100"
    assert chart["kind"] == billboard.SONGS
    assert chart["entries"][0] == {"rank": 1, "artist": "Rihanna Featuring Jay-Z",
                                   "track": "Umbrella"}


def test_artists_chart_is_detected_by_the_repeated_name():
    html = page("Greatest of All Time Artists", [
        {"rank": 1, "primary": "The Beatles", "secondary": "The Beatles"},
        {"rank": 2, "primary": "Elton John", "secondary": "Elton John"},
    ])
    chart = billboard.parse_chart(html)
    assert chart["kind"] == billboard.ARTISTS
    assert [e["artist"] for e in chart["entries"]] == ["The Beatles", "Elton John"]
    assert all(e["track"] == "" for e in chart["entries"])


def test_a_single_casing_mismatch_does_not_flip_the_chart_kind():
    """בעמוד האמיתי שורה אחת מתוך 125 כתובה JAY-Z מול Jay-Z."""
    rows = [{"rank": i, "primary": f"Artist {i}", "secondary": f"Artist {i}"}
            for i in range(1, 20)]
    rows.append({"rank": 20, "primary": "JAY-Z", "secondary": "Jay-Z"})
    chart = billboard.parse_chart(page("Artists", rows))
    assert chart["kind"] == billboard.ARTISTS


def test_entries_come_back_in_rank_order():
    html = page("Hot 100", [
        {"rank": 3, "primary": "C", "secondary": "Artist C"},
        {"rank": 1, "primary": "A", "secondary": "Artist A"},
        {"rank": 2, "primary": "B", "secondary": "Artist B"},
    ])
    assert [e["rank"] for e in billboard.parse_chart(html)["entries"]] == [1, 2, 3]


def test_a_page_that_is_not_a_chart_returns_empty_without_raising():
    for html in ("", "<html><body><p>שלום</p></body></html>", None):
        chart = billboard.parse_chart(html)
        assert chart["entries"] == []


def test_slug_is_stable_and_filesystem_safe():
    assert billboard.chart_slug("Greatest of All Time Artists") == "greatest-of-all-time-artists"
    assert billboard.chart_slug("Hot 100 / Songs!") == "hot-100-songs"
    assert billboard.chart_slug("") == "chart"
