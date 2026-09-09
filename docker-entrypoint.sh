#!/bin/sh
# מייצר את `.streamlit/secrets.toml` בעלייה, ואז מריץ את Streamlit.
#
# **למה בכלל צריך את זה.** Streamlit 1.62 קורא secrets מקובץ או מתיקיית
# secrets בלבד (אופציית `secrets.files`) — **לא ממשתני סביבה**. הקובץ
# עצמו מכיל client secret ולכן הוא ב-`.gitignore`, כלומר הוא לא קיים
# בקונטיינר. בלי הגשר הזה `[auth]` לעולם לא מוגדר בפרודקשן,
# `accounts.login_available()` מחזיר False, וכפתור ההתחברות לא מרונדר
# בכלל — וזו בדיוק הסיבה שהוא לא נראה עד היום.
set -e

SECRETS=".streamlit/secrets.toml"

if [ -f "$SECRETS" ]; then
    # קובץ שהגיע בדרך אחרת (mount, bake) מנצח. לא דורסים סוד קיים.
    echo "auth: using the existing $SECRETS"
elif [ -n "$GOOGLE_CLIENT_ID" ] && [ -n "$GOOGLE_CLIENT_SECRET" ] \
     && [ -n "$APP_URL" ] && [ -n "$COOKIE_SECRET" ]; then
    # חיתוך `/` מסיים: `redirect_uri` חייב להסתיים ב-`/oauth2callback`
    # בדיוק (Streamlit מאמת את זה), ו-URL עם סלאש כפול לא יתאים למה
    # שרשום ב-Google Cloud Console.
    BASE=$(printf '%s' "$APP_URL" | sed 's:/*$::')
    mkdir -p .streamlit
    umask 077
    cat > "$SECRETS" <<TOML
[auth]
redirect_uri = "${BASE}/oauth2callback"
cookie_secret = "${COOKIE_SECRET}"

[auth.google]
client_id = "${GOOGLE_CLIENT_ID}"
client_secret = "${GOOGLE_CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
TOML
    echo "auth: enabled for ${BASE}"
else
    # פיצ'ר בלי מפתח הוא פיצ'ר כבוי ולא קריסה — אותה מוסכמה כמו
    # `YOUTUBE_API_KEY`. אבל **הגדרה חלקית נאמרת בקול**, אחרת מי
    # שהגדיר שלושה מתוך ארבעה משתנים היה מחפש שעה למה הכפתור נעלם.
    MISSING=""
    for name in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET APP_URL COOKIE_SECRET; do
        eval "value=\$$name"
        [ -z "$value" ] && MISSING="$MISSING $name"
    done
    if [ -n "$GOOGLE_CLIENT_ID$GOOGLE_CLIENT_SECRET$APP_URL$COOKIE_SECRET" ]; then
        echo "auth: DISABLED — missing:$MISSING"
    else
        echo "auth: not configured (sign-in hidden)"
    fi
fi

exec streamlit run app.py --server.port="${PORT:-8501}" --server.address=0.0.0.0
