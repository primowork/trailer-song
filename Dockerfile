FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ה-entrypoint מייצר את `.streamlit/secrets.toml` ממשתני סביבה לפני
# שהוא מריץ את Streamlit, ואז מריץ אותו על הפורט הדינמי של Railway.
# בלי זה `[auth]` לא קיים בקונטיינר וההתחברות לגוגל נשארת כבויה — ראו
# את ההערה בראש הסקריפט.
RUN chmod +x docker-entrypoint.sh
CMD ["./docker-entrypoint.sh"]
