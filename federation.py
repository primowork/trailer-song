"""בדיקת רפרטואר מול הפדרציה הישראלית לתקליטים וקלטות (ifpi.co.il).

הערה על היעד: גרסאות קודמות פנו ל-federation.co.il, שהוא ארגון אחר לגמרי
(הפדרציה לקניין רוחני ומלחמה בסחר בלתי חוקי, אתר WordPress). השדות artName/trkName
ו-CategoryID=94 נכתבו עבור אותו אתר שגוי ולכן מעולם לא נמצאו, מה שגרם ל-Timeout של
30 שניות לכל אסטרטגיה. הפדרציה לתקליטים היא ifpi.co.il, אתר ASP, ומנוע הרפרטואר שלה
הוא search.asp ("רפרטואר הפדרציה").

שמות השדות בטופס אינם ידועים מראש וניתנים להגדרה דרך משתני סביבה, כדי שאפשר יהיה
לכייל אותם מול ה-HTML האמיתי בלי לשנות קוד. ראה FIELD_CANDIDATES ו-README.
"""
import os
import urllib.parse
from dataclasses import asdict, dataclass

import httpx
from bs4 import BeautifulSoup
from thefuzz import fuzz

import storage
from search import clean_artist_name, clean_track_title

FEDERATION_URL = os.environ.get("IFPI_SEARCH_URL", "https://www.ifpi.co.il/search.asp")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# מועמדים לשמות שדה הטופס. הראשון שנמצא בדף בפועל הוא זה שבשימוש, כך שאין צורך
# לנחש נכון מראש. אפשר לכפות שם מדויק דרך משתנה סביבה.
ARTIST_FIELD_CANDIDATES = [
    os.environ.get("IFPI_ARTIST_FIELD"),
    "artName", "artist", "Artist", "txtArtist", "ArtistName", "performer",
]
TRACK_FIELD_CANDIDATES = [
    os.environ.get("IFPI_TRACK_FIELD"),
    "trkName", "track", "Track", "txtTrack", "TrackName", "song", "SongName",
]
SUBMIT_SELECTOR = 'input[type="submit"], input[type="image"], button[type="submit"], input[value="חפש"]'

APPROVED = "APPROVED"
NOT_FOUND = "NOT_FOUND"
UNKNOWN = "UNKNOWN"

NO_RESULTS_MARKERS = ("לא נמצאו תוצאות", "לא נמצאו רשומות", "לא נמצאו")

PUBLISHER_HINTS = (
    "יוניברסל", "וורנר", "סוני", "הליקון", "אן.אמ.סי", "מיוצג",
    "nmc", "bmg", "universal", "sony", "warner", "helicon",
)
# "מיוצג בפדרציה ע\"י" הוא הכיתוב האמיתי באתר. הכתיב "מייצג" לבדו לא תפס אותו.
PUBLISHER_HEADERS = ("מיוצג", "מייצג", "חברה", "מפיץ", "בעל זכויות", "לייבל", "יצרן")

# מילות הכותרת שמזהות את שורת הכותרות בטבלת התוצאות
HEADER_MARKERS = ("המבצע", "הקלטה", "אלבום", "מיוצג")

ARTIST_MATCH_THRESHOLD = 85
TRACK_MATCH_THRESHOLD = 80
PUBLISHER_COLUMN_FALLBACK = 4

# פרק זמן קצר בכוונה: שדה שאינו קיים צריך להיכשל בשניות, לא ב-30 שניות כפול
# שלוש אסטרטגיות כפול כל שיר באצווה.
FIELD_TIMEOUT_MS = 5000
NAV_TIMEOUT_MS = 30000
# אתר ASP ותיק שנטען מדאטה-סנטר מחוץ לישראל יכול להיות איטי. 10 שניות היו צרות מדי.
PREFLIGHT_TIMEOUT = 20.0
PREFLIGHT_ATTEMPTS = 2

# אתר הפדרציה אינו נגיש מחלק מספקי הענן: הבקשות פשוט לא מקבלות תשובה
# (timeout, לא סירוב). IFPI_PROXY מנתב את הבקשות דרך יציאה שכן מגיעה אליו,
# למשל proxy בישראל. חל גם על httpx וגם על Playwright.
PROXY = os.environ.get("IFPI_PROXY", "").strip()


def _http_client(timeout: float = 10.0) -> httpx.Client:
    kwargs = {"follow_redirects": True, "timeout": timeout}
    if PROXY:
        kwargs["proxy"] = PROXY
    return httpx.Client(**kwargs)


@dataclass
class VerifyResult:
    status: str = UNKNOWN
    publisher: str = ""
    confidence: int = 0
    matched_row: str = ""
    strategy: str = ""
    error: str = ""

    @property
    def approved(self) -> bool:
        return self.status == APPROVED

    def to_dict(self) -> dict:
        return asdict(self)


def _first_present_field(html: str, candidates) -> str:
    """בוחר את שם השדה הראשון מבין המועמדים שקיים בפועל בדף."""
    soup = BeautifulSoup(html, "html.parser")
    names = {i.get("name") for i in soup.find_all(["input", "select"]) if i.get("name")}
    lowered = {n.lower(): n for n in names}
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in names:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def _row_columns(element) -> list[str]:
    """עמודות של שורה: תאי טבלה, ואם אין — ה-div-ים הישירים שבתוכה."""
    cells = element.find_all(["td", "th"], recursive=False)
    if not cells:
        cells = element.find_all(["td", "th"])
    if not cells:
        cells = element.find_all("div", recursive=False)
    return [cell.get_text(" ", strip=True) for cell in cells]


def _extract_rows(soup) -> list[list[str]]:
    """שורות התוצאה, בין אם הן <tr> ובין אם הן div-ים צפים.

    ifpi.co.il לא משתמש ב-<table> בכלל: טבלת התוצאות שם בנויה מ-div-ים עם
    float, ולכן חיפוש <tr> בלבד החזיר "לא נמצאה טבלה" על כל דף תוצאות אמיתי.
    """
    rows = [_row_columns(tr) for tr in soup.find_all("tr")]
    rows = [cols for cols in rows if cols]
    if rows:
        return rows

    # שורות שהאתר מסמן במפורש (המנגנון שפותח את פרטי ההקלטה)
    marked = soup.find_all("div", class_="om")
    rows = [cols for cols in (_row_columns(div) for div in marked) if len(cols) >= 2]
    if rows:
        # לשורת הכותרות אין class="om", ובלעדיה אינדקס עמודת המו"ל היה נשען על
        # ברירת מחדל קשיחה במקום על מה שכתוב בדף
        header = _find_header_row(soup)
        return ([header] + rows) if header else rows

    # נפילה לאחור: כל div שהילדים הישירים שלו הם כמה div-ים עם טקסט
    for div in soup.find_all("div"):
        children = div.find_all("div", recursive=False)
        if len(children) < 4:
            continue
        cols = [c.get_text(" ", strip=True) for c in children]
        if sum(1 for c in cols if c) >= 3:
            rows.append(cols)
    return rows


def _is_header_row(cols: list[str]) -> bool:
    return sum(1 for c in cols if any(m in c for m in HEADER_MARKERS)) >= 2


def _find_header_row(soup) -> list[str] | None:
    """שורת הכותרות של טבלת התוצאות, שאינה מסומנת כשורה רגילה."""
    for div in soup.find_all("div"):
        children = div.find_all("div", recursive=False)
        if len(children) < 3:
            continue
        cols = [c.get_text(" ", strip=True) for c in children]
        if _is_header_row(cols):
            return cols
    return None


def _publisher_index(rows: list[list[str]]) -> int | None:
    """אינדקס עמודת המו"ל, לפי שורת הכותרות."""
    for cols in rows[:6]:
        if sum(1 for c in cols if any(m in c for m in HEADER_MARKERS)) < 2:
            continue
        for idx, header in enumerate(cols):
            if any(h in header for h in PUBLISHER_HEADERS):
                return idx
    return None





def parse_ifpi_table(html_content: str, target_artist: str, target_track: str = "") -> VerifyResult:
    """מנתח את תוצאת החיפוש. דורש התאמה של אמן *וגם* שיר."""
    if not html_content:
        return VerifyResult(status=UNKNOWN, error="תוכן ריק")

    try:
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception as exc:
        return VerifyResult(status=UNKNOWN, error=f"פרסור נכשל: {exc}")

    text = soup.get_text(" ", strip=True)
    if any(marker in text for marker in NO_RESULTS_MARKERS):
        return VerifyResult(status=NOT_FOUND, confidence=95)

    rows = _extract_rows(soup)
    if not rows:
        return VerifyResult(status=UNKNOWN, error="לא נמצאה טבלת תוצאות")

    clean_artist = clean_artist_name(target_artist).lower()
    clean_track = clean_track_title(target_track).lower()
    publisher_idx = _publisher_index(rows)

    best = VerifyResult(status=NOT_FOUND, confidence=60)

    for cols in rows:
        if not cols or _is_header_row(cols):
            continue
        row_text = " ".join(cols).lower()

        artist_score = fuzz.token_set_ratio(clean_artist, row_text) if clean_artist else 0
        track_score = fuzz.partial_ratio(clean_track, row_text) if clean_track else 0

        if artist_score < ARTIST_MATCH_THRESHOLD:
            continue
        if clean_track and track_score < TRACK_MATCH_THRESHOLD:
            continue

        publisher = ""
        if publisher_idx is not None and len(cols) > publisher_idx:
            publisher = cols[publisher_idx]
        if not publisher and len(cols) > PUBLISHER_COLUMN_FALLBACK:
            publisher = cols[PUBLISHER_COLUMN_FALLBACK]
        publisher = publisher.strip()

        if not publisher or publisher in {"-", "--"} or len(publisher) < 2:
            continue

        confidence = int((artist_score + (track_score if clean_track else artist_score)) / 2)
        if any(hint in publisher.lower() for hint in PUBLISHER_HINTS):
            confidence = min(100, confidence + 10)

        if confidence > best.confidence or best.status != APPROVED:
            best = VerifyResult(
                status=APPROVED,
                publisher=publisher,
                confidence=min(confidence, 100),
                matched_row=" | ".join(cols)[:300],
            )

    return best


def all_input_names(html: str) -> list[str]:
    """כל שמות ה-input/select בדף — למקרה שאף מועמד לא מתאים."""
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return []
    names = []
    for element in soup.find_all(["input", "select"]):
        name = element.get("name")
        if name and name not in names and element.get("type") != "hidden":
            names.append(name)
    return names


def learn_fields_from_html(html: str) -> dict:
    """לומד את שמות שדות החיפוש מדף שהמשתמש הדביק, ושומר אותם.

    האתר חוסם את השרת, ולכן preflight מעולם לא ראה את הטופס ושמות השדות
    ב-*_FIELD_CANDIDATES הם ניחוש. הדפדפן של המשתמש כן מגיע לאתר.
    """
    artist = _first_present_field(html, ARTIST_FIELD_CANDIDATES)
    track = _first_present_field(html, TRACK_FIELD_CANDIDATES)
    result = {
        "artist_field": artist,
        "track_field": track,
        "all_inputs": all_input_names(html),
    }
    if artist or track:
        storage.save_federation_fields(
            {"artist_field": artist, "track_field": track})
    return result


def set_fields(artist_field: str, track_field: str) -> bool:
    """קביעה ידנית, כשהזיהוי האוטומטי לא מצא את השדות הנכונים."""
    return storage.save_federation_fields(
        {"artist_field": artist_field, "track_field": track_field})


def learned_fields() -> dict:
    """שמות השדות בתוקף: משתנה סביבה קודם, אחרת מה שנלמד מהדף."""
    stored = storage.load_federation_fields()
    return {
        "artist_field": os.environ.get("IFPI_ARTIST_FIELD") or stored.get("artist_field", ""),
        "track_field": os.environ.get("IFPI_TRACK_FIELD") or stored.get("track_field", ""),
    }


def build_search_url(artist: str, track: str) -> str:
    """קישור חיפוש מוכן, לפתיחה בדפדפן של המשתמש.

    בלי שמות שדות ידועים מחזיר את הכתובת הבסיסית — עדיף מקישור עם פרמטרים שגויים.
    """
    fields = learned_fields()
    params = {}
    if fields["artist_field"] and artist:
        params[fields["artist_field"]] = " ".join(clean_artist_name(artist).split()[:2])
    if fields["track_field"] and track:
        params[fields["track_field"]] = clean_track_title(track) or track
    if not params:
        return FEDERATION_URL
    return f"{FEDERATION_URL}?{urllib.parse.urlencode(params)}"


def verify_from_html(html: str, artist: str, track: str) -> VerifyResult:
    """פסק דין מתוך HTML שהמשתמש הדביק — אותה לוגיקה כמו במסלול האוטומטי."""
    result = parse_ifpi_table(html, artist, track)
    result.strategy = "הדבקה ידנית"
    return result


def _looks_like_results_page(html: str) -> bool:
    if not html or len(html) < 500:
        return False
    if any(marker in html for marker in NO_RESULTS_MARKERS):
        return True
    return "<tr" in html.lower()


class FormNotFoundError(RuntimeError):
    """טופס החיפוש לא נמצא בדף — כתובת שגויה או שהמבנה השתנה."""


class FederationClient:
    """דפדפן אחד לכל האצווה, עם preflight שנכשל מהר כשהטופס לא קיים.

    with FederationClient() as fed:
        result = fed.verify(track)
    """

    def __init__(self, use_http_fast_path: bool = True, debug: bool = False):
        self.use_http_fast_path = use_http_fast_path
        self.debug = debug
        self.last_html = ""
        self.artist_field = ""
        self.track_field = ""
        self.preflight_error = ""
        self._preflight_done = False
        self._playwright = None
        self._browser = None
        self._page = None
        self._http = _http_client()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        for closer in (
            lambda: self._page and self._page.close(),
            lambda: self._browser and self._browser.close(),
            lambda: self._playwright and self._playwright.stop(),
            lambda: self._http.close(),
        ):
            try:
                closer()
            except Exception:
                pass
        self._page = self._browser = self._playwright = None

    # ---------- preflight ----------

    def _fetch_preflight_html(self) -> tuple[str, str]:
        """מביא את דף החיפוש. מחזיר (html, שגיאה).

        קודם httpx, ואם הוא נכשל — דרך הדפדפן. הדפדפן שולח טביעת TLS וכותרות
        אמיתיות ומריץ JS, ולכן מצליח לעיתים במקומות ש-httpx נחסם או קורס בהם.
        כישלון של httpx לבדו אינו סיבה לוותר על כל האצווה.
        """
        http_error = ""
        for attempt in range(PREFLIGHT_ATTEMPTS):
            try:
                response = self._http.get(FEDERATION_URL, headers={"User-Agent": USER_AGENT},
                                          timeout=PREFLIGHT_TIMEOUT)
                return response.text, ""
            except Exception as exc:
                http_error = str(exc) or exc.__class__.__name__

        # httpx לא הצליח: מנסים דרך הדפדפן לפני שמוותרים
        self.use_http_fast_path = False
        try:
            page = self._ensure_page()
            page.goto(FEDERATION_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            return page.content(), ""
        except Exception as exc:
            browser_error = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            both_timed_out = "timed out" in http_error.lower() and "timeout" in browser_error.lower()
            if both_timed_out and not PROXY:
                hint = (
                    "שני המסלולים עשו timeout, כלומר הבקשות לא מקבלות תשובה כלל — "
                    "האתר אינו נגיש מהרשת של השרת (חומת אש או חסימה גאוגרפית), "
                    "ולא מדובר בתקלת קוד. הגדר IFPI_PROXY לכתובת proxy שמגיע לאתר, "
                    "או הרץ את האפליקציה מרשת שממנה האתר נגיש."
                )
            elif both_timed_out:
                hint = f"שני המסלולים עשו timeout גם דרך ה-proxy שהוגדר ({PROXY})."
            else:
                hint = "בדוק במסך ההגדרות 'בדוק חיבור לפדרציה'."
            return "", (
                f"לא ניתן לטעון את {FEDERATION_URL}. "
                f"HTTP: {http_error[:80]}. דפדפן: {browser_error[:80]}. {hint}"
            )

    def preflight(self) -> bool:
        """טוען את דף החיפוש פעם אחת ומזהה את שמות שדות הטופס.

        נכשל מהר ומסמן את כל האצווה כ-UNKNOWN במקום לבזבז timeout לכל שיר.
        """
        if self._preflight_done:
            return not self.preflight_error

        self._preflight_done = True
        html, error = self._fetch_preflight_html()
        if error:
            self.preflight_error = error
            return False

        if self.debug:
            self.last_html = html

        self.artist_field = _first_present_field(html, ARTIST_FIELD_CANDIDATES)
        self.track_field = _first_present_field(html, TRACK_FIELD_CANDIDATES)

        # שמות שנלמדו הם נפילה לאחור לזיהוי מהדף החי, ורק כשבדף בכלל יש טופס.
        # אחרת דף שגיאה היה "מצליח" preflight רק כי פעם נלמדו שמות.
        if not self.artist_field and not self.track_field and all_input_names(html):
            learned = learned_fields()
            self.artist_field = learned["artist_field"]
            self.track_field = learned["track_field"]

        if not self.artist_field and not self.track_field:
            self.preflight_error = (
                f"הדף {FEDERATION_URL} נטען, אך לא זוהה בו אף שדה חיפוש מוכר. "
                "הגדר IFPI_ARTIST_FIELD ו-IFPI_TRACK_FIELD לשמות האמיתיים מהטופס."
            )
            return False
        return True

    # ---------- מסלול HTTP ----------

    def _http_search(self, artist: str, track: str) -> str:
        params = {}
        if self.artist_field:
            params[self.artist_field] = artist
        if self.track_field:
            params[self.track_field] = track
        try:
            response = self._http.get(FEDERATION_URL, params=params,
                                      headers={"User-Agent": USER_AGENT}, timeout=10.0)
            html = response.text
        except Exception:
            return ""
        return html if _looks_like_results_page(html) else ""

    # ---------- מסלול Playwright ----------

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        }
        if PROXY:
            launch_kwargs["proxy"] = {"server": PROXY}
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        context = self._browser.new_context(user_agent=USER_AGENT)
        self._page = context.new_page()
        return self._page

    def _browser_search(self, artist: str, track: str) -> str:
        page = self._ensure_page()
        page.goto(FEDERATION_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

        filled = False
        if self.artist_field:
            page.fill(f'[name="{self.artist_field}"]', artist, timeout=FIELD_TIMEOUT_MS)
            filled = True
        if self.track_field:
            page.fill(f'[name="{self.track_field}"]', track, timeout=FIELD_TIMEOUT_MS)
            filled = True
        if not filled:
            raise FormNotFoundError(self.preflight_error or "לא זוהו שדות טופס")

        with page.expect_navigation(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS):
            page.locator(SUBMIT_SELECTOR).first.click(timeout=FIELD_TIMEOUT_MS)
        page.wait_for_timeout(1000)
        return page.content()

    def _search(self, artist: str, track: str) -> str:
        if self.use_http_fast_path:
            html = self._http_search(artist, track)
            if html:
                return html
        return self._browser_search(artist, track)

    # ---------- API ----------

    def verify(self, track: dict) -> VerifyResult:
        if not self.preflight():
            return VerifyResult(status=UNKNOWN, error=self.preflight_error, strategy="preflight")

        raw_artist = track.get("artist") or track.get("artistName") or ""
        raw_song = track.get("track") or track.get("trackName") or ""

        clean_song = clean_track_title(raw_song)
        clean_artist = clean_artist_name(raw_artist)
        short_artist = " ".join(clean_artist.split()[:2])

        strategies = [
            ("אמן + שיר", short_artist, clean_song, 0),
            ("שיר בלבד", "", clean_song, 5),
            ("אמן בלבד", short_artist, "", 20),
        ]

        last_error = ""
        saw_response = False

        for name, artist_param, track_param, penalty in strategies:
            if not artist_param and not track_param:
                continue
            # אין טעם באסטרטגיה שדורשת שדה שלא קיים בטופס
            if artist_param and not self.artist_field:
                continue
            if track_param and not self.track_field:
                continue
            try:
                html = self._search(artist_param, track_param)
            except FormNotFoundError as exc:
                return VerifyResult(status=UNKNOWN, error=str(exc), strategy="preflight")
            except Exception as exc:
                last_error = str(exc)
                continue

            saw_response = True
            if self.debug:
                self.last_html = html

            result = parse_ifpi_table(html, raw_artist, raw_song if track_param else "")
            result.strategy = name
            if result.status == APPROVED:
                result.confidence = max(0, result.confidence - penalty)
                return result

        if not saw_response:
            return VerifyResult(status=UNKNOWN, error=last_error or "כל הניסיונות נכשלו")
        return VerifyResult(status=NOT_FOUND, confidence=70, strategy="כל האסטרטגיות")

    def verify_many(self, tracks: list[dict], progress_cb=None) -> list[VerifyResult]:
        results = []
        total = len(tracks)
        for index, track in enumerate(tracks):
            results.append(self.verify(track))
            if progress_cb:
                progress_cb(index + 1, total, track)
        return results


REACH_TIMEOUT = 3.0


def _tcp_reachable(host: str, port: int, timeout: float) -> tuple[bool, str]:
    """בדיקת TCP גולמית משותפת: מצליח לפתוח חיבור? עם הודעת שגיאה לדיווח.

    זו בדיקת חיבור בלבד ולא preflight מלא: מצב הכשל בפועל הוא timeout ברמת
    החיבור (IP של דאטה-סנטר שנחסם), וה-preflight המלא עולה עד 20 שניות —
    יקר מדי לבדיקה שרצה מאליה.
    """
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except Exception as exc:
        return False, str(exc)[:80] or exc.__class__.__name__


def reachable(url: str = FEDERATION_URL, timeout: float = REACH_TIMEOUT) -> bool:
    """האם השרת בכלל מצליח לפתוח חיבור לאתר הפדרציה.

    כשמוגדר proxy הבדיקה הישירה אינה רלוונטית ולכן מדלגים עליה.
    """
    if PROXY:
        return True
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ok, _ = _tcp_reachable(host, port, timeout)
    return ok


def diagnose(url: str = FEDERATION_URL) -> dict:
    """אבחון חיבור לאתר הפדרציה, לשימוש הממשק.

    נועד לענות על השאלה שאי אפשר לענות עליה מהקוד: האם השרת שמריץ את
    האפליקציה בכלל מגיע לאתר, וכמה זמן זה לוקח.
    """
    import socket
    import time
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    report = {"url": url, "host": host, "proxy": PROXY or "לא מוגדר"}

    started = time.time()
    try:
        report["ip"] = socket.gethostbyname(host)
        report["dns"] = "תקין"
    except Exception as exc:
        report["dns"] = f"נכשל: {exc}"
        report["elapsed"] = round(time.time() - started, 1)
        return report

    # חיבור TCP ישיר: מפריד בין "האתר לא עונה" ל"שגיאת HTTP"
    started = time.time()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ok, error = _tcp_reachable(host, port, 10)
    report["tcp"] = "תקין" if ok else f"נכשל: {error}"
    report["tcp_seconds"] = round(time.time() - started, 1)

    started = time.time()
    try:
        with _http_client(PREFLIGHT_TIMEOUT) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})
        report["http_status"] = response.status_code
        report["bytes"] = len(response.content)
        html = response.text
        report["artist_field"] = _first_present_field(html, ARTIST_FIELD_CANDIDATES) or "לא נמצא"
        report["track_field"] = _first_present_field(html, TRACK_FIELD_CANDIDATES) or "לא נמצא"
        report["html"] = html
    except Exception as exc:
        report["http_status"] = f"נכשל: {str(exc)[:120] or exc.__class__.__name__}"
    report["elapsed"] = round(time.time() - started, 1)
    return report
