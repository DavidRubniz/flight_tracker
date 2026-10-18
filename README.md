# ✈ Flight Tracker — מעקב מחירי טיסות מישראל

אפליקציה מקומית שעוקבת אחרי מחירי טיסות מנתב"ג (TLV) ליעדים או לאזורים שלמים (אירופה, ארה"ב, אסיה...), כולל טיסות עם קונקשנים. היא שומרת היסטוריית מחירים ושולחת התראה כשמחיר יורד מתחת ליעד שהגדרתם, או כשמופיעה "מציאה" (ירידה חדה מהממוצע).

- **Backend:** FastAPI + APScheduler + SQLite
- **UI:** ממשק Web מקומי (Tailwind + Alpine.js + Chart.js), בעברית ומימין לשמאל
- **מקורות נתונים:** SerpApi (Google Flights), Duffel, Travelpayouts, או מצב דמו בלי מפתח
- **התראות:** התראות שולחן עבודה, Telegram, אימייל

---

## התחלה מהירה

צריך [uv](https://docs.astral.sh/uv/) מותקן (uv מתקין לבד את Python 3.12 אם הוא חסר):

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
uv sync --all-extras          # יוצר .venv ומתקין הכל (כולל כלי פיתוח)
cp .env.example .env          # ב-Windows: copy .env.example .env
uv run flight-tracker         # מפעיל את השרת ופותח את הדפדפן בכתובת http://127.0.0.1:8000
```

ב-`.env.example` מוגדר `FLIGHT_PROVIDER=mock`, כך שהאפליקציה רצה על **נתוני דמו** (מחירים מציאותיים שמשתנים לאט) ואפשר לנסות את כל המסכים מיד.
אם בוחרים ספק אמיתי בלי למלא את המפתח שלו, השרת לא יעלה ויציג הודעת שגיאה ברורה. הסיבה: נתוני דמו לא אמורים להתערבב בהיסטוריית המחירים האמיתית.

> 💡 **כשעוברים מדמו לספק אמיתי** כדאי למחוק את `data/flights.db` (כשהשרת כבוי), כדי שהממוצעים וה"נמוך ביותר שנצפה" יחושבו רק ממחירים אמיתיים.
כדי לא לפתוח דפדפן אוטומטית: `uv run flight-tracker --no-browser`.

---

## מקורות נתונים: מה לחבר?

> ⚠️ **Amadeus Self-Service כבר לא זמין.** Amadeus סגרה את פורטל ה-Self-Service ב-17 ביולי 2026 ומפתחות ה-API שלו בוטלו. נשארה רק גישת Enterprise בחוזה, ולכן הוא לא נכלל כאן.

| ספק | `FLIGHT_PROVIDER` | מה מקבלים | עלות | מתי להשתמש |
|---|---|---|---|---|
| **SerpApi – Google Flights** ⭐ | `serpapi` | מחירים בזמן אמת מ-Google Flights, כולל קונקשנים, חברות ושעות | מסלול חינמי מוגבל ואחריו בתשלום | **מומלץ.** הכי אמין ומקיף |
| **Duffel** | `duffel` | הצעות חיות ישירות מחברות התעופה (NDC), ניתנות להזמנה | חיפוש ללא עלות, עמלה על הזמנה | כשרוצים מחירים "אמיתיים" מהחברות |
| **Travelpayouts (Aviasales)** | `travelpayouts` | מחירים מ-cache של חיפושים אחרונים | חינם | סריקות רחבות וזולות לאיתור מציאות |
| דמו | `mock` | נתונים מדומים | חינם | פיתוח והדגמה |

**למה לא Scraping (BeautifulSoup/Playwright)?** אתרי טיסות (Google Flights, Skyscanner, Kayak) בנויים כולם על JavaScript, מוגנים מבוטים (CAPTCHA, טביעות אצבע) ומשנים מבנה בתדירות גבוהה. Scraper כזה נשבר כל כמה שבועות, ולרוב גם מפר את תנאי השימוש. ה-API של Skyscanner פתוח רק לשותפים עסקיים. SerpApi מטפל בכל זה בשבילכם ומחזיר JSON יציב.

### הגדרת מפתחות
1. **SerpApi:** נרשמים ב-[serpapi.com](https://serpapi.com), מעתיקים את ה-API Key ל-`SERPAPI_API_KEY` ומגדירים `FLIGHT_PROVIDER=serpapi`.
2. **Duffel:** נרשמים ב-[duffel.com](https://duffel.com) ויוצרים Access Token ל-`DUFFEL_ACCESS_TOKEN`. טוקן `duffel_test_...` מחזיר את חברת הבדיקה "Duffel Airways", ולמחירים אמיתיים צריך טוקן live.
3. **Travelpayouts:** נרשמים ב-[travelpayouts.com](https://www.travelpayouts.com), ובקטע Developers → API token מעתיקים ל-`TRAVELPAYOUTS_TOKEN`.

💡 **עלות קריאות:** כל יעד = מספר תאריכים × מספר שדות תעופה. אזור "אירופה" (10 שדות) עם 3 תאריכים הוא 30 קריאות לכל סריקה. במסלול חינמי כדאי לסרוק בתדירות נמוכה ולצמצם תאריכים.

### התראות Telegram
1. ב-Telegram פותחים שיחה עם `@BotFather`, שולחים `/newbot` ומעתיקים את ה-token ל-`TELEGRAM_BOT_TOKEN`.
2. שולחים הודעה כלשהי לבוט החדש, ואז פותחים בדפדפן `https://api.telegram.org/bot<TOKEN>/getUpdates` ומעתיקים את `chat.id` ל-`TELEGRAM_CHAT_ID`.
3. מפעילים מחדש, מסמנים "Telegram" במסך ההגדרות ולוחצים "שלח בדיקה".

### התראות אימייל (Gmail)
צריך להפעיל אימות דו-שלבי, ליצור [App Password](https://myaccount.google.com/apppasswords) ולמלא `SMTP_USER`, `SMTP_PASSWORD` ו-`EMAIL_TO`.

---

## איך זה עובד

1. **Scheduler** מריץ סריקה כל X שעות (ברירת מחדל: 12, ניתן לשינוי ב-UI). הסריקה הבאה מחושבת מזמן הסריקה האחרונה ששמורה במסד, כך שהפעלה מחדש של השרת **לא** גורמת לסריקה נוספת ולא מבזבזת מכסת API. רק בהפעלה הראשונה, או כשהסריקה כבר באיחור, הסריקה רצה תוך 5 שניות.
2. לכל יעד פעיל נבנות שאילתות לפי: שדות תעופה (אזור מתפרק לכמה שדות) × "ימים קדימה" (ברירת מחדל: בעוד 45 יום, ואפשר להוסיף עוד תאריכים) × מספר לילות.
3. השאילתות רצות במקביל (עד 3 בו-זמנית), עם retry ו-backoff אקספוננציאלי לשגיאות רשת, 429 ו-5xx.
4. נשמרות 15 ההצעות הזולות, ובנוסף "snapshot" של המחיר המינימלי, שממנו נבנים הגרף והמגמה.
5. **כללי התראה** (`services/pricing.py`):
   - 🎯 **יעד:** המחיר הזול ≤ מחיר היעד שהוגדר.
   - 🔥 **מציאה:** המחיר נמוך ב-N% מהממוצע של 30 הימים האחרונים (נדרשות לפחות 3 דגימות).
   - אין התראה חוזרת על אותו מחיר או מחיר גבוה ממנו בתוך חלון ה-cooldown.

---

## מבנה הקוד

```
flights_prices/
├── pyproject.toml             # תלויות, כלי פיתוח, הגדרות ruff/mypy/pytest
├── .env.example               # כל משתני הסביבה עם הסבר
├── src/flight_tracker/
│   ├── __main__.py            # נקודת כניסה (CLI) → uvicorn
│   ├── config.py              # הגדרות סטטיות וסודות מ-.env (pydantic-settings)
│   ├── models.py              # כל מודלי הנתונים (Pydantic) – "השפה" של המערכת
│   ├── regions.py             # הגדרת אזורים ושמות שדות תעופה
│   ├── database.py            # שכבת SQLite – ה-SQL היחיד בפרויקט
│   ├── providers/             # מקורות נתונים
│   │   ├── base.py            #   ממשק FlightProvider + retry + היררכיית שגיאות
│   │   ├── serpapi.py · duffel.py · travelpayouts.py · mock.py
│   │   └── __init__.py        #   create_provider() – factory
│   ├── notifications/         # ערוצי התראה
│   │   ├── base.py            #   ממשק Notifier
│   │   ├── desktop.py · telegram.py · mail.py
│   │   └── __init__.py        #   NotificationDispatcher – שליחה לכל הערוצים הפעילים
│   ├── services/              # לוגיקה עסקית
│   │   ├── pricing.py         #   כללים טהורים: מתי מתריעים, מגמה (ללא I/O)
│   │   ├── tracker.py         #   מנוע הסריקה
│   │   ├── scheduler.py       #   תזמון ברקע
│   │   └── dashboard.py       #   הרכבת נתוני לוח הבקרה
│   ├── api/
│   │   ├── container.py       #   Composition root – כל החיבורים בין הרכיבים במקום אחד
│   │   ├── routes.py          #   REST endpoints  (/api/...)
│   │   └── app.py             #   FastAPI factory + lifespan
│   └── static/                # ה-UI: index.html · app.js · styles.css
└── tests/                     # pytest (כולל mock ל-HTTP עם respx)
```

**זרימת תלויות** (חד-כיוונית, אין מעגלים):
`api → services → providers / notifications / database → models`

### עקרונות
- **כל תלות מוזרקת** דרך `api/container.py`, כך שקל להחליף רכיב או ליצור fake בבדיקות (ראו `tests/test_tracker.py`).
- **לוגיקה טהורה מופרדת מ-I/O:** את כללי ההתראה (`services/pricing.py`) אפשר לבדוק בלי DB ובלי רשת.
- **שגיאות מסווגות:** `ProviderAuthError` עוצרת את הסריקה כולה (אין טעם להמשיך עם מפתח שגוי), ואילו `ProviderError` רגילה נרשמת ומוצגת ב-UI בלי להפיל את הסריקה.
- **סודות** נשמרים רק ב-`.env` (כ-`SecretStr`). **הגדרות משתמש** נשמרות ב-DB ונערכות מה-UI.

---

## פיתוח

```bash
uv run pytest                 # בדיקות
uv run ruff check .           # lint
uv run ruff format .          # פורמט אוטומטי
uv run mypy                   # בדיקת טיפוסים (strict)
uv run uvicorn flight_tracker.api.app:create_app --factory --reload   # שרת עם hot-reload
```

תיעוד API אינטראקטיבי (Swagger) זמין בכתובת http://127.0.0.1:8000/docs.

### מתכונים לשינויים נפוצים

**הוספת מקור נתונים חדש**
1. צרו `providers/my_source.py` עם מחלקה שיורשת מ-`FlightProvider` ומממשת `async def search(query) -> list[FlightOffer]`. את הקריאות עושים דרך `self._request_json(...)`, שמספק retry ומיפוי שגיאות בחינם.
2. הוסיפו ערך ל-`ProviderName` ב-`config.py`, שדה למפתח, ו-`case` ב-`create_provider()`.
3. הוסיפו בדיקה עם `respx` (ראו `tests/test_providers.py`).

**הוספת ערוץ התראה** (למשל WhatsApp/Slack)
1. צרו מחלקה שיורשת מ-`Notifier` ב-`notifications/`.
2. חברו אותה ב-`NotificationDispatcher` והוסיפו `notify_xxx` ל-`AppSettings`.
3. ב-UI הוסיפו שורה למערך `channels` ב-`static/app.js`.

**שינוי כללי ההתראה:** הכל נמצא ב-`services/pricing.py`, יחד עם הבדיקות ב-`tests/test_pricing.py`.

**הוספת אזור:** מוסיפים שורה ל-`REGIONS` ב-`regions.py`.

**שינוי שדה ב-DB:** `database.py` מכיל את הסכמה. אין מערכת מיגרציות, כך שבשינוי סכמה בפיתוח פשוט מוחקים את `data/flights.db`. אם הפרויקט יגדל, מומלץ לעבור ל-SQLAlchemy + Alembic.
