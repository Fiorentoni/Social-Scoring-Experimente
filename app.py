import json
import os
import threading
from datetime import timedelta, datetime, timezone
from time import strftime
from typing import Any
import requests
import json

from flask import Flask, jsonify, request, render_template, session, redirect, \
    url_for, Response
from werkzeug import Response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # In Produktion (HTTPS) aktivieren:
    # SESSION_COOKIE_SECURE=True,
)

# Konfiguration
FILENAME = 'score.json'

# TODO add same for diary
# test

HEADERS = {
    "Authorization": f"token {os.environ.get('GITHUB_TOKEN')}",
    "Accept": "application/vnd.github.v3+json"
}

STARTING_SCORE = 4.0
BASE_SCORE_CHANGE = 0.05
SCORE_COOLDOWN_HOURS = timedelta(hours=12)


USERS = {
    "Annika": {"display_name": "Annika", "password": "latein"},
    "Jonas": {"display_name": "Jonas", "password": "pazifik"},
    "Tesniem": {"display_name": "Tesniem", "password": "paradies"},
    "Nele": {"display_name": "Nele", "password": "biologie"},
    "Nelly": {"display_name": "Nelly", "password": "stern"},
    "Anna-Lena": {"display_name": "Anna-Lena", "password": "ozean"},
    "Levin": {"display_name": "Levin", "password": "informatik"},
    "Fynn": {"display_name": "Fynn", "password": "spitze"},
    "Sadiyah": {"display_name": "Sadiyah", "password": "sprache"},
    "Jan-Luca": {"display_name": "Jan-Luca", "password": "wald"},
    "Samuel": {"display_name": "Samuel", "password": "blitz"},
    "admin": {"display_name": "Admin", "password": "admin"},
}

# Gemeinsamer Zustand + Synchronisation für Long-Polling
state_lock = threading.Lock()
version_condition = threading.Condition(state_lock)
update_version = 0  # wird hochgezählt, wenn sich etwas ändert

def get_gist_data():
    """Lädt die JSON-Daten aus dem Gist."""
    response = requests.get(f"https://api.github.com/gists/{os.environ.get("GIST_ID")}")
    if response.status_code == 200:
        gist_content = response.json()
        file_data = gist_content['files'][FILENAME]['content']
        return json.loads(file_data)
    else:
        print("Fehler beim Laden:", response.status_code)
        return {}

def update_gist_data(new_data_list):
    """Speichert die komplette Liste zurück in den Gist."""
    payload = {
        "files": {
            FILENAME: {
                "content": json.dumps(new_data_list, indent=4)
            }
        }
    }
    response = requests.patch(f"https://api.github.com/gists/{os.environ.get("GIST_ID")}",
                              headers=HEADERS,
                              json=payload)
    return response.status_code == 200


def load_current_state() -> Any:
    global update_version

    if not get_gist_data():
        initial = {
            "version": 0,
            "persons": [
                {"id": 1, "name": "Annika", "photo": None, "score": STARTING_SCORE},
                {"id": 2, "name": "Jonas", "photo": None, "score": STARTING_SCORE},
                {"id": 3, "name": "Tesniem", "photo": None, "score": STARTING_SCORE},
                {"id": 4, "name": "Nele", "photo": None, "score": STARTING_SCORE},
                {"id": 5, "name": "Nelly", "photo": None, "score": STARTING_SCORE},
                {"id": 6, "name": "Anna-Lena", "photo": None, "score": STARTING_SCORE},
                {"id": 7, "name": "Levin", "photo": None, "score": STARTING_SCORE},
                {"id": 8, "name": "Fynn", "photo": None, "score": STARTING_SCORE},
                {"id": 9, "name": "Sadiyah", "photo": None, "score": STARTING_SCORE},
                {"id": 10, "name": "Jan-Luca", "photo": None, "score": STARTING_SCORE},
                {"id": 11, "name": "Samuel", "photo": None, "score": STARTING_SCORE},
            ],
            "vote_log": {}
        }

        update_gist_data(initial)

            # TODO add diary filling

    data = get_gist_data()
    update_version = data.get("version", 0)

    return data

def save_state(data: object) -> None:
    update_gist_data(data)

def get_utc_now():
    return datetime.now(timezone.utc)

def convert_to_iso_zulu(date_time: datetime) -> str:
    # ISO-Format mit Z (UTC)
    return date_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def convert_from_iso_zulu(string: str) -> datetime:
    # robustes Parsen von ISO-Strings mit Z
    if string.endswith("Z"):
        string = string[:-1] + "+00:00"
    return datetime.fromisoformat(string)
# Globaler Zustand im Speicher
current_state = load_current_state()

# TODO brauchen wir wirklich Jquery?

def bump_version() -> None:
    global update_version
    update_version += 1
    current_state["version"] = update_version
    save_state(current_state)
    version_condition.notify_all()


def current_user() -> Any | None:
    user = session.get("user")
    return user if user in USERS else None


def ensure_logged_in_api() -> tuple[Response, int] | None:
    if not current_user():
        return jsonify({"error": "Nicht eingeloggt"}), 401
    return None


@app.route("/login", methods=["GET", "POST"])
def render_login() -> str | Response:
    # Bereits eingeloggt? Weiterleiten.
    if current_user():
        return redirect(url_for("render_index"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        # Demo-Check: Passwort == Benutzername
        if username in USERS and password == USERS[username]["password"]:
            session.permanent = True  # Session-Cookie wird "permanent" (Ablauf lt. app.permanent_session_lifetime)
            session["user"] = username
            nxt = request.args.get("next")
            return redirect(nxt or url_for("render_index"))
        else:
            error = "Benutzername oder Passwort falsch."

    return render_template("login.html", error=error)


@app.route("/logout", methods=["GET"])
def render_logout() -> Response:
    session.clear()
    return redirect(url_for("render_login"))


@app.route("/")
def render_index() -> Response | str:
    if not current_user():
        return redirect(url_for("render_login", next=request.path))
    user = current_user()
    user_score = "User ohne Score"
    for person in current_state["persons"]:
        if person["name"] == user:
            user_score = person["score"]
    return render_template("index.html",
                           logged_in_user=user,
                           display_name=USERS[user]["display_name"],
                           user_score=user_score)


@app.route("/api/persons", methods=["GET"])
def get_persons() -> tuple[Response, int] | Response:
    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged
    with state_lock:
        return jsonify({"version": update_version, "persons": current_state["persons"]})

def can_vote_now(user: str, person_id: int, desired_operation: str) -> tuple[bool, None] | tuple[bool, Any]:
    """
    True/None, wenn voten erlaubt.
    False/remaining_timedelta, wenn gesperrt.
    """
    vote_log = current_state.get("vote_log", {})
    vote_log_per_person = vote_log.get(str(person_id), {})
    vote_log_per_person_for_user = vote_log_per_person.get(user, {})
    recorded_operation = vote_log_per_person_for_user.get(desired_operation, {})
    if not vote_log_per_person_for_user or not recorded_operation:
        return True, None
    try:
        last_timestamp = convert_from_iso_zulu(recorded_operation.get("timestamp"))
    except Exception:
        # Defekter Eintrag? Vorsichtshalber sperre nicht.
        return True, None
    delta = get_utc_now() - last_timestamp
    if delta >= SCORE_COOLDOWN_HOURS:
        return True, None
    else:
        return False, (SCORE_COOLDOWN_HOURS - delta)
def record_vote(user: str, person_id: int, operation: str, comment: str) -> None:
    """
    Vote im Log vermerken (Zeitpunkt + Operation).
    Muss unter state_lock aufgerufen werden.
    """
    # Wenn Key im Dictionary, dann returne ihn. Ansonsten setze default.
    vote_log = current_state.setdefault("vote_log", {})
    vote_log_per_person = vote_log.setdefault(str(person_id), {})
    vote_log_per_person_for_user = vote_log_per_person.setdefault(str(user), {})
    vote_log_per_person_for_user[operation] = {"timestamp": convert_to_iso_zulu(get_utc_now()),
                                 "comment": comment}

@app.route("/api/persons/<int:person_id>/inc", methods=["POST"])
def increase_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | Response:
    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged
    user = current_user()
    with state_lock:
        allowed, remaining = can_vote_now(user, person_id, "inc")
        if not allowed:
            return jsonify({
                "error": "Cooldown aktiv: Du kannst diese Person nur alle 12 Stunden upvoten.",
                "retry_after_seconds": int(remaining.total_seconds())
            }), 429

        comment = request.form.get("comment")

        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Person nicht gefunden"}), 404

        person["score"] = round(person["score"] + BASE_SCORE_CHANGE, 2)
        record_vote(user, person_id, "inc", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

@app.route("/api/persons/<int:person_id>/dec", methods=["POST"])
def decrease_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | Response:
    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged
    user = current_user()
    with state_lock:
        allowed, remaining = can_vote_now(user, person_id, "dec")
        if not allowed:
            return jsonify({
                "error": "Cooldown aktiv: Du kannst diese Person nur alle 12 Stunden downvoten.",
                "retry_after_seconds": int(remaining.total_seconds())
            }), 429

        comment = request.form.get("comment")

        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Person nicht gefunden"}), 404

        person["score"] = round(person["score"] - BASE_SCORE_CHANGE, 2)
        record_vote(user, person_id, "dec", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

# def calculate_vote_weight():



@app.route("/api/updates", methods=["GET"])
def long_poll_updates() -> tuple[Response, int] | Response:
    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0

    with version_condition:
        if update_version <= since:
            version_condition.wait(timeout=25.0)
        changed = update_version > since
        return jsonify({"changed": changed, "version": update_version, "persons": current_state["persons"]})


if __name__ == "__main__":
    # Debug nur lokal; für Produktion WSGI-Server nutzen
    app.run(debug=True, threaded=True)