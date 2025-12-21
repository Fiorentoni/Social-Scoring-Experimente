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

# TODO auf FAST API umstellen

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
RANKING_PERCENTAGES = {
    9.10: 1,
    18.19: 2,
    27.28: 3,
    36.37: 4,
    45.46: 5,
    54.56: 6,
    63.65: 7,
    72.74: 8,
    81.83: 9,
    90.92: 10,
    100.0: 11
}
VOTE_WEIGHTS = { #TODO halbieren?
    1: 0.5,
    2: 0.4,
    3: 0.3,
    4: 0.2,
    5: 0.1,
    6: 0.09,
    7: 0.08,
    8: 0.07,
    9: 0.06,
    10: 0.05,
    11: 0.04
}
VOTE_WEIGHT_ADMIN = 0.2
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
    "admin": {"display_name": "Admin", "password": "speck"},
}

# Gemeinsamer Zustand + Synchronisation für Long-Polling
state_lock = threading.Lock()
gist_lock = threading.Lock()
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
    data = get_gist_data()

    with gist_lock:
        if not data:
            data = {
                "version": 0,
                "persons": [
                    {"id": 1, "name": "Annika", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 2, "name": "Jonas", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 3, "name": "Tesniem", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 4, "name": "Nele", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 5, "name": "Nelly", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 6, "name": "Anna-Lena", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 7, "name": "Levin", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 8, "name": "Fynn", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 9, "name": "Sadiyah", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 10, "name": "Jan-Luca", "photo": None, "score": STARTING_SCORE, "privileges": None},
                    {"id": 11, "name": "Samuel", "photo": None, "score": STARTING_SCORE, "privileges": None},
                ],
                "vote_log": {}
            }

            update_gist_data(data)

            # TODO add diary filling

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

def get_ranking_category(person):
    sorted_scorelist = get_sorted_scorelist()
    for user in sorted_scorelist:
        if user['name'] == person['name']:
            ranking = sorted_scorelist.index(user) + 1 # weil liste bei 0 anfängt!
            ranking_percentage = ranking / len(sorted_scorelist) * 100
            ranking_percentages_list = list(RANKING_PERCENTAGES)
            match ranking_percentage:
                case r if r <= ranking_percentages_list[0]:
                    return 1
                case r if r <= ranking_percentages_list[1]:
                    return 2
                case r if r <= ranking_percentages_list[2]:
                    return 3
                case r if r <= ranking_percentages_list[3]:
                    return 4
                case r if r <= ranking_percentages_list[4]:
                    return 5
                case r if r <= ranking_percentages_list[5]:
                    return 6
                case r if r <= ranking_percentages_list[6]:
                    return 7
                case r if r <= ranking_percentages_list[7]:
                    return 8
                case r if r <= ranking_percentages_list[8]:
                    return 9
                case r if r <= ranking_percentages_list[9]:
                    return 10
                case r if r <= ranking_percentages_list[10]:
                    return 11
                case _:
                    return "Ungültiger Wert!"

            # TODO was wenn keiner gefunden?

def get_vote_weight(person):
    if person["name"] == "admin":
        return VOTE_WEIGHT_ADMIN

    ranking_category = get_ranking_category(person)
    vote_weight = VOTE_WEIGHTS[ranking_category]
    return vote_weight

def get_privileges(person):
    ranking_category = get_ranking_category(person)
    privileges = []

    if ranking_category == 1:
        privileges.append(["Darf einzelne Privilegien nach Absprache mit Lehrkraft an Andere weitergeben", "green"])
        privileges.append(["Darf Unterrichtsentscheidungen mitbestimmen (z.B. jetzt ein Video schauen oder mehr Zeit für eine Aufgabe oder Umfang der Hausaufgaben", "green"])
        privileges.append(["Darf einzelne negative Effekte nach Absprache mit Lehrkraft bei Anderen aufheben", "green"])
    if  1 <= ranking_category <= 3:
        privileges.append(["Verspätungen werden nicht negativ gewertet", "green"])
        privileges.append(["Erhält ab und zu Snacks/Getränke von der Lehrkraft", "green"])
        privileges.append(["Hat einen Joker bei der Zufallsauswahl", "green"])
        privileges.append(["Keine verpflichtenden Hausaufgaben", "green"])
        privileges.append(["Zusätzliche WLAN-Zugänge", "green"])
        privileges.append(["Darf im Unterricht essen", "green"])
    if  1 <= ranking_category <= 5:
        privileges.append(["Auge zu bei leicht verspäteten Entschuldigungen", "green"])
        privileges.append(["Kommt zuerst bei Notenbesprechung", "green"])
    if 6 <= ranking_category  <= 11:
        privileges.append(["Ab und zu nur die Untersten in Zufallsauswahl", "red"])
        privileges.append(["Darf nicht früher gehen", "red"])
    if 8 <= ranking_category <= 11:
        privileges.append(["Lehrkraft bestimmt Sitzplatz", "red"])
        privileges.append(["iPad muss flach auf dem Tisch liegen", "red"])
    if ranking_category == 11:
        privileges.append(["Muss 1x pro Woche Kuchen (oder gesunde Snacks) mitbringen", "red"])

    return privileges

def get_sorted_scorelist():
    return sorted(current_state["persons"], key = lambda person: person["score"], reverse = True)

def add_privileges_to_state(state):
    for person in state["persons"]:
        person["privileges"] = get_privileges(person)

    return state

def bump_version() -> None:
    global update_version
    global current_state
    update_version += 1
    current_state["version"] = update_version
    save_state(current_state)

    # Update current_state mit Privilegien nur im lokalen Speicher
    current_state = add_privileges_to_state(current_state)
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
    person = get_current_person()
    user_score = person["score"] # TODO BUG!
    return render_template("index.html",
                           logged_in_user=user,
                           display_name=USERS[user]["display_name"],
                           user_score=user_score)

def get_current_person():
    if current_user() == "admin":
        return {"name": "admin", "score": 0.0}

    for person in current_state["persons"]:
        if person["name"] == current_user():
            current_person = person

    return current_person


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
    current_person = get_current_person()
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

        vote_weight = get_vote_weight(current_person)
        person["score"] = round(person["score"] + vote_weight, 2)
        record_vote(user, person_id, "inc", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

@app.route("/api/persons/<int:person_id>/dec", methods=["POST"])
def decrease_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | Response:
    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged
    user = current_user()
    current_person = get_current_person()
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

        vote_weight = get_vote_weight(current_person)
        person["score"] = round(person["score"] - vote_weight, 2)
        record_vote(user, person_id, "dec", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

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


######### Globaler Zustand im Speicher
current_state = load_current_state()
current_state = add_privileges_to_state(current_state)
#########

# TODO brauchen wir wirklich Jquery?

if __name__ == "__main__":
    # Debug nur lokal; für Produktion WSGI-Server nutzen
    app.run(debug=True, threaded=True)