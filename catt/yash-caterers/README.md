# YASH CATERERS website

## Run
    pip install -r requirements.txt
    python app.py                 # http://localhost:5000   (development)
    gunicorn -w 2 -b 0.0.0.0:8000 app:app   # production

- Customer site: `/`   Owner login: three-dot menu (⋮) → ADMIN LOGIN, or `/admin/login`
- Initial owner password: the one you supplied. Only its PBKDF2-SHA256 hash is stored (in code seed + SQLite `admin` table).
- Data: `instance/yash_caterers.db` (SQLite). Back this file up. Set `YASH_DATA_DIR` to keep it elsewhere.
- Behind HTTPS in production set `YASH_SECURE_COOKIES=1` (and optionally `YASH_SECRET_KEY`).
- Your six videos are in `static/media/` exactly as uploaded (byte-identical), shown in the original order.
