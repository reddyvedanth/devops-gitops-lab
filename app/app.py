import os
import socket
import threading

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
import psycopg

app = Flask(__name__)
app.jinja_env.autoescape = True

_schema_ready = False
_schema_lock = threading.Lock()

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Notes 2</title>
  <style>
    body { font-family: sans-serif; margin: 2rem auto; max-width: 36rem; line-height: 1.4; }
    form { display: flex; gap: .5rem; }
    input { flex: 1; padding: .45rem .6rem; }
    button { padding: .45rem .8rem; }
    li { margin: .45rem 0; }
    small { color: #555; }
    footer { color: #555; margin-top: 2rem; font-size: .9rem; }
  </style>
</head>
<body>
  <h1>Notes 2</h1>
  <form method="post" action="/notes">
    <input name="body" maxlength="280" placeholder="Write a note" required>
    <button type="submit">Save</button>
  </form>
  <ul>
  {% for note in notes %}
    <li>{{ note.body }} <small>{{ note.created_at }}</small></li>
  {% else %}
    <li>No notes yet. This database starts empty, and a restart clears it.</li>
  {% endfor %}
  </ul>
  <footer>pod {{ pod }} · version {{ version }}</footer>
</body>
</html>
"""


def connect():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
    )


def ensure_schema(conn):
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn.execute(
            """
            create table if not exists notes (
                id bigint generated always as identity primary key,
                body text not null,
                created_at timestamptz not null default now()
            )
            """
        )
        conn.commit()
        _schema_ready = True


def fetch_notes(conn):
    rows = conn.execute(
        """
        select id, body, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')
        from notes
        order by id desc
        limit 20
        """
    ).fetchall()
    return [{"id": row[0], "body": row[1], "created_at": row[2]} for row in rows]


def note_body():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        body = payload.get("body", "")
    else:
        body = request.form.get("body", "")
    return body.strip()


@app.get("/")
def home():
    try:
        with connect() as conn:
            ensure_schema(conn)
            notes = fetch_notes(conn)
    except Exception:
        app.logger.exception("could not read notes")
        return jsonify(status="not-ready"), 503
    return render_template_string(
        PAGE,
        notes=notes,
        pod=socket.gethostname(),
        version=os.getenv("APP_VERSION", "dev"),
    )


@app.get("/notes")
def list_notes():
    try:
        with connect() as conn:
            ensure_schema(conn)
            notes = fetch_notes(conn)
    except Exception:
        app.logger.exception("could not list notes")
        return jsonify(status="not-ready"), 503
    return jsonify(notes=notes)


@app.post("/notes")
def create_note():
    body = note_body()
    if not body:
        return jsonify(error="body is required"), 400
    if len(body) > 280:
        return jsonify(error="body must be 280 characters or fewer"), 400
    try:
        with connect() as conn:
            ensure_schema(conn)
            row = conn.execute(
                """
                insert into notes (body)
                values (%s)
                returning id, body, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')
                """,
                (body,),
            ).fetchone()
            conn.commit()
    except Exception:
        app.logger.exception("could not insert note")
        return jsonify(status="not-ready"), 503
    if request.is_json:
        return jsonify(id=row[0], body=row[1], created_at=row[2]), 201
    return redirect(url_for("home"), code=303)


@app.get("/version")
def version():
    return jsonify(
        release="practice-2",
        version=os.getenv("APP_VERSION", "dev"),
        pod=socket.gethostname(),
    )


@app.get("/health")
def health():
    return jsonify(status="ok"), 200


@app.get("/ready")
def ready():
    try:
        with connect() as conn:
            ensure_schema(conn)
            conn.execute("select 1")
    except Exception:
        app.logger.exception("database not ready")
        return jsonify(status="not-ready"), 503
    return jsonify(status="ready"), 200
