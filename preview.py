"""שליפת בייטים של preview דרך השרת, כמעקף לחסימת CORS.

`decodeAudioData` דורש את הבייטים דרך `fetch`, ולכן דורש `Access-Control-Allow-Origin`
מהשרת שמארח את ה-preview. נגינה ב-`<audio>` עובדת בלי זה, פענוח לא. כשהחנות חוסמת,
השרת מושך את הבייטים בעצמו ומגיש אותם לרכיב כ-data URI — הפענוח והמדידה נשארים
בדפדפן, בלי תלות ניתוח אודיו בשרת.

זו נפילה לאחור ולא ברירת המחדל: היא מעבירה מגה-בייטים דרך השרת ודרך הדף.
"""
import base64

import httpx

TIMEOUT = 20.0
MAX_BYTES = 3 * 1024 * 1024   # preview של 30 שניות הוא כמה מאות KB; זה כבר חריג
DEFAULT_TYPE = "audio/mpeg"


def fetch_data_uri(url: str) -> tuple[str, str]:
    """מחזיר (data_uri, error). לא זורק חריגות."""
    if not url:
        return "", "אין preview"
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
    except Exception as exc:
        return "", f"השרת לא הצליח למשוך את ה-preview: {str(exc)[:80]}"

    if not data:
        return "", "קובץ ריק"
    if len(data) > MAX_BYTES:
        return "", f"ה-preview גדול מדי ({len(data) // 1024}KB)"

    media_type = (response.headers.get("content-type") or DEFAULT_TYPE).split(";")[0]
    if not media_type.startswith("audio"):
        media_type = DEFAULT_TYPE
    return f"data:{media_type};base64,{base64.b64encode(data).decode()}", ""
