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
    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

STARTING_SCORE = 4.0
VOTE_WEIGHT_MODIFIER = 1 #TODO halbieren?
VOTE_WEIGHT_ADMIN = 0.2
DEFAULT_VOTE_WEIGHT = 0.1
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
VOTE_WEIGHTS = {
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
VOTE_COOLDOWN_HOURS = timedelta(hours=12)

MAX_SIZE_VOTE_LOG = 15


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
        print("Fehler beim Laden:", response.text)
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

# TODO requests verhindern durch caching, sonst vielleicht Probleme mit GIT-TOKEN RATE LIMIT?!

def load_current_state() -> Any:
    global update_version
    data = get_gist_data()

    # TODO Prevent overwriting of GIST file!
    # TODO do not SAVE privileges to JSON!
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
            # Wenn gleiche Punktzahl, dann Ranking aufstufen
            if ranking != 1:
                while ranking != 1 and sorted_scorelist[ranking-1]['score'] == sorted_scorelist[ranking-2]['score']:
                    ranking = ranking - 1

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

    return None


def get_vote_weight(person):
    global current_state

    if person["name"] == "admin":
        return VOTE_WEIGHT_ADMIN * VOTE_WEIGHT_MODIFIER

    global update_version
    number_of_persons = len(current_state["persons"])
    if update_version <= number_of_persons * 2:
        return DEFAULT_VOTE_WEIGHT

    ranking_category = get_ranking_category(person)
    vote_weight = VOTE_WEIGHTS[ranking_category] * VOTE_WEIGHT_MODIFIER
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
    global current_state

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
    global current_state

    if current_user() == "admin":
        return {"id": -10, "name": "admin", "score": 0.0, "privileges": []}

    current_person = None

    for person in current_state["persons"]:
        if person["name"] == current_user():
            current_person = person

    return current_person

def get_structured_vote_log(vote_log):
    flat_list = []

    # 1. Struktur auflösen (Flatten)
    for people in vote_log.items():
        person_name = people[0]
        for actions in people[1].items():
            action_type = actions[0]
            # Wir erstellen ein flaches Dictionary pro Eintrag
            flat_entry = {
                "person": person_name,
                "operation": action_type,
                "timestamp": actions[1]["timestamp"],
                "comment": actions[1]["comment"]
            }
            if flat_entry["comment"] != "null":
                flat_list.append(flat_entry)

    # 2. Sortieren nach Timestamp (neueste zuerst)
    # Da ISO-Strings (YYYY-MM-DD) sortierbar sind, reicht ein String-Vergleich
    flat_list.sort(key=lambda x: x["timestamp"], reverse=True)

    # 3. Umwandeln in lokalen Timestamp
    for item in flat_list:
        timestamp = item["timestamp"]
        item['timestamp'] = convert_from_iso_zulu(timestamp).strftime("%d.%m.%Y, %H:%M:%S")

    return flat_list

def cut_vote_log():
    global current_state

    # Vote-Log aus dem globalen State abrufen
    # Struktur: {"1": [votes], "2": [votes], ...}
    vote_log = current_state["vote_log"]

    if not vote_log:
        return

    flat_list = []
    # Über jede Person (Key) im Log iterieren
    for person in vote_log:
        for votedBy in vote_log[person]:
            for vote in vote_log[person][votedBy]:
                flat_entry = {
                    "person": votedBy,
                    "operation": vote,
                    "timestamp": vote_log[person][votedBy][vote]["timestamp"],
                    "comment": vote_log[person][votedBy][vote]["comment"]
                }
                # Votes, deren Cooldown abgelaufen ist und die keinen Kommentar haben, kann man weglassen
                timestamp_dt = convert_from_iso_zulu(flat_entry["timestamp"])
                delta = get_utc_now() - timestamp_dt
                if flat_entry["comment"] != "null" or delta <= VOTE_COOLDOWN_HOURS:
                    flat_list.append(flat_entry)

        # Nach Zeit sortieren
        flat_list.sort(key=lambda x: x["timestamp"], reverse=True)

        # Auf die 15 neuesten Einträge kürzen
        kept_entries = flat_list[:MAX_SIZE_VOTE_LOG]

        # Das Dictionary für diese Person neu aufbauen
        new_person_vote_log = {}
        for entry in kept_entries:
            voter = entry["person"]
            operation = entry["operation"]
            timestamp = entry["timestamp"]
            comment = entry["comment"]

            if voter not in new_person_vote_log:
                new_person_vote_log[voter] = {}

            # TODO add eben operation!
            new_person_vote_log[voter][operation]["timestamp"] = entry["timestamp"]
            new_person_vote_log[voter][operation]["comment"] = entry["comment"]

            # Den aktualisierten State zurückschreiben
            current_state["vote_log"][person] = new_person_vote_log

@app.route("/api/persons", methods=["GET"])
def get_persons() -> tuple[Response, int] | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    cut_vote_log()

    own_id = get_current_person()["id"]
    cooldowns = get_current_cooldowns()
    plus_cooldowns = cooldowns[0]
    minus_cooldowns = cooldowns[1]

    with state_lock:
        return jsonify({"version": update_version, "persons": current_state["persons"], "plusCooldowns": plus_cooldowns,
                        "minusCooldowns": minus_cooldowns,
                        "own_vote_log": get_structured_vote_log(current_state["vote_log"].get(str(own_id), {}))})

#TODO ergänze "gelesen" bei VoteLog und das automatische Ausblenden / alternativ manuell gelesen markierne
# TODO laternativ: Votes haben id und bei "Gelesen" wird das Vote mit der entsprechenden Id gelöscht
#  (zu viele Abfragen aber; stattdessen als gelöscht markiert nur?)

def get_current_cooldowns():
    global current_state

    plus_cooldowns = []
    minus_cooldowns = []
    user = current_user()

    for person in current_state["persons"]:
        if not can_vote_now(user, person["id"], "inc"):
            plus_cooldowns.append(person["name"])
        if not can_vote_now(user, person["id"], "dec"):
            minus_cooldowns.append(person["name"])

    return plus_cooldowns, minus_cooldowns

def can_vote_now(user: str, person_id: int, desired_operation: str) -> tuple[bool, None] | bool:
    """
    True/None, wenn voten erlaubt.
    False/remaining_timedelta, wenn gesperrt.
    """
    global current_state

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
    remaining_cooldown = VOTE_COOLDOWN_HOURS - delta
    if delta >= VOTE_COOLDOWN_HOURS: # TODO fix
        return True
    else:
        return False

def record_vote(user: str, person_id: int, operation: str, comment: str) -> None:
    """
    Vote im Log vermerken (Zeitpunkt + Operation).
    Muss unter state_lock aufgerufen werden.
    """
    global current_state

    #TODO votes nachzählen pro Person - wenn zu viele, dann löschen, um Speicherplatz zu sparen
    # Wenn Key im Dictionary, dann returne ihn. Ansonsten setze default.
    vote_log = current_state.setdefault("vote_log", {})
    vote_log_per_person = vote_log.setdefault(str(person_id), {})
    vote_log_per_person_for_user = vote_log_per_person.setdefault(str(user), {})
    vote_log_per_person_for_user[operation] = {"timestamp": convert_to_iso_zulu(get_utc_now()),
                                               "comment": comment}

@app.route("/api/persons/<int:person_id>/inc", methods=["POST"])
def increase_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | bool | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    # Nicht für eigene Person voten
    if person_id == get_current_person()['id']:
        return jsonify({"error": "Es kann nicht für die eigene Person abgestimmt werden."}), 428

    user = current_user()
    current_person = get_current_person()
    with state_lock:
        allowed = can_vote_now(user, person_id, "inc")
        if not allowed:
            return jsonify({
                "error": "Cooldown aktiv: Du kannst diese Person nur alle 12 Stunden upvoten.",}), 429

        comment = request.form.get("comment")

        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Person nicht gefunden"}), 404

        if person["score"] == 5:
            return jsonify({"error": "Die Person hat schon den höchsten Score erreicht."}), 427

        vote_weight = get_vote_weight(current_person)
        person["score"] = min(round(person["score"] + vote_weight, 2), 5)
        record_vote(user, person_id, "inc", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

@app.route("/api/persons/<int:person_id>/dec", methods=["POST"])
def decrease_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | bool | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    # Nicht für eigene Person voten
    if person_id == get_current_person()['id']:
        return jsonify({"error": "Es kann nicht für die eigene Person abgestimmt werden."}), 428

    user = current_user()
    current_person = get_current_person()
    with state_lock:
        allowed = can_vote_now(user, person_id, "dec")
        if not allowed:
            return jsonify({
                "error": "Cooldown aktiv: Du kannst diese Person nur alle 12 Stunden downvoten.",}), 429

        comment = request.form.get("comment")

        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Person nicht gefunden"}), 404

        if person["score"] == 0:
            return jsonify({"error": "Die Person hat schon den niedrigsten Score erreicht."}), 427

        # nicht unter 0.0 scoren
        vote_weight = get_vote_weight(current_person)
        person["score"] = max(round(person["score"] - vote_weight, 2),0)
        record_vote(user, person_id, "dec", comment)  # Vote vermerken
        bump_version()
        return jsonify({"version": update_version, "person": person})

@app.route("/api/updates", methods=["GET"])
def long_poll_updates() -> tuple[Response, int] | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0

    cut_vote_log()

    own_id = get_current_person()["id"]
    cooldowns = get_current_cooldowns()
    plus_cooldowns = cooldowns[0]
    minus_cooldowns = cooldowns[1]
#
    with version_condition:
        if update_version <= since:
            version_condition.wait(timeout=25.0)
        changed = update_version > since
        return jsonify({"changed": changed, "version": update_version, "persons": current_state["persons"],
                        "plusCooldowns": plus_cooldowns, "minusCooldowns": minus_cooldowns,
                        "own_vote_log": get_structured_vote_log(current_state["vote_log"].get(str(own_id), {}))}), 200


######### Globaler Zustand im Speicher
current_state = load_current_state()
current_state = add_privileges_to_state(current_state)
#########

# TODO brauchen wir wirklich Jquery?

if __name__ == "__main__":
    # Debug nur lokal; für Produktion WSGI-Server nutzen
    app.run(debug=True, threaded=True)