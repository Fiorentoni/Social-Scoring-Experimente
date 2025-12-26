import json
import os
import threading
from datetime import timedelta, datetime, timezone
from time import strftime
from typing import Any
import requests
import json

from flask import Flask, jsonify, request, render_template, session, redirect, \
    url_for, Response, send_file
from werkzeug import Response
from fpdf import FPDF
import io

# Framework configuration
app = Flask(__name__)

@app.template_filter('initials')
def initials_filter(name):
    if not name:
        return '??'
    parts = name.strip().split()
    a = parts[0][0] if len(parts) > 0 and len(parts[0]) > 0 else ''
    b = parts[1][0] if len(parts) > 1 and len(parts[1]) > 0 else ''
    return (a + b).upper()
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
DIARY_FILENAME = 'diary.json'

GIST_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

STARTING_SCORE = 3.0
VOTE_WEIGHT_MODIFIER = 0.5
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

# Globaler Admin-User (Passwort aus Umgebungsvariable oder Default)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "speck")

USERS = {
    "admin": {"display_name": "Admin", "password": ADMIN_PASSWORD},
}

# Gemeinsamer Zustand + Synchronisation für Long-Polling
state_lock = threading.Lock()
gist_lock = threading.Lock()
diary_lock = threading.Lock()
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
        response.raise_for_status()

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
                              headers=GIST_HEADERS,
                              json=payload)
    return response.status_code == 200

def get_diary_data():
    """Lädt die JSON-Daten aus dem Diary."""
    response = requests.get(f"https://api.github.com/gists/{os.environ.get("DIARY")}")
    if response.status_code == 200:
        gist_content = response.json()
        file_data = gist_content['files'][DIARY_FILENAME]['content']
        return json.loads(file_data)
    else:
        print("Fehler beim Laden des Tagebuchs:", response.text)
        return None

# State configuration
def load_current_state() -> Any:
    global update_version

    try:
        data = get_gist_data()
    except Exception as e:
        print(f"KRITISCHER FEHLER beim Laden der Gist-Daten: {e}")
        # Hier Programm abbrechen oder einen Fallback-Mechanismus nutzen,
        # der NICHT das Gist überschreibt.
        raise SystemExit("App konnte Daten nicht laden und wird beendet, um Datenverlust zu vermeiden.")

    # with gist_lock:
    #     if not data:
    #         data = {
    #             "version": 0,
    #             "persons": [
    #                 {"id": 1, "name": "Annika", "password": "latein", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 2, "name": "Jonas", "password": "pazifik", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 3, "name": "Tesniem", "password": "paradies", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 4, "name": "Nele", "password": "biologie", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 5, "name": "Nelly", "password": "stern", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 6, "name": "Anna-Lena", "password": "ozean", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 7, "name": "Levin", "password": "informatik", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 8, "name": "Fynn", "password": "spitze", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 9, "name": "Sadiyah", "password": "sprache", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 10, "name": "Jan-Luca", "password": "wald", "photo": None, "score": STARTING_SCORE},
    #                 {"id": 11, "name": "Samuel", "password": "blitz", "photo": None, "score": STARTING_SCORE},
    #             ],
    #             "vote_log": {}
    #         }
    #
    #         update_gist_data(data)

    update_version = data.get("version", 0)

    return data

def save_state(data: object) -> bool:
    with gist_lock:
        success = update_gist_data(data)
        if not success:
            print("FEHLER beim Speichern der Gist-Daten.")
        return success

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

def get_ranking_category(person, sorted_scorelist):
    for index, user in enumerate(sorted_scorelist):
        if user['name'] == person['name']:
            ranking = index + 1 # weil liste bei 0 anfängt!
            # Wenn gleiche Punktzahl, dann Ranking aufstufen
            if ranking != 1:
                while ranking != 1 and sorted_scorelist[ranking-1]['score'] == sorted_scorelist[ranking-2]['score']:
                    ranking = ranking - 1

            ranking_percentage = ranking / len(sorted_scorelist) * 100
            
            # Effizientere Suche nach der Kategorie
            for threshold, category in RANKING_PERCENTAGES.items():
                if ranking_percentage <= threshold:
                    return category
            return 11 # Default / Letzte Kategorie

    return None


def get_vote_weight(person, ranking_category=None):
    global current_state
    global update_version

    if person["name"] == "admin":
        return VOTE_WEIGHT_ADMIN * VOTE_WEIGHT_MODIFIER

    number_of_persons = len(current_state["persons"])
    if update_version <= number_of_persons * 2:
        return DEFAULT_VOTE_WEIGHT

    if ranking_category is None:
        sorted_list = get_sorted_scorelist()
        ranking_category = get_ranking_category(person, sorted_list)
        
    vote_weight = VOTE_WEIGHTS.get(ranking_category, 0.04) * VOTE_WEIGHT_MODIFIER
    return round(vote_weight, 2)


def get_privileges(person, ranking_category=None):
    if ranking_category is None:
        sorted_list = get_sorted_scorelist()
        ranking_category = get_ranking_category(person, sorted_list)
    
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

def add_ranking_category_to_state(state):
    sorted_list = sorted(state["persons"], key=lambda p: p["score"], reverse=True)
    
    # Kategorien für alle bestimmen
    for person in state["persons"]:
        category = get_ranking_category(person, sorted_list)
        person["ranking_category"] = category
        person["privileges"] = get_privileges(person, category)

    return state

def remove_ranking_category_from_state(state):
    for person in state["persons"]:
        person.pop("ranking_category", None)
        person.pop("privileges", None)

def bump_version() -> bool:
    global update_version
    global current_state

    # Wir inkrementieren die Version lokal
    update_version += 1
    current_state["version"] = update_version
    cut_vote_log()
    remove_ranking_category_from_state(current_state)

    success = save_state(current_state)
    
    # Privilegien wieder hinzufügen für die Anzeige
    add_ranking_category_to_state(current_state)
    
    if success:
        version_condition.notify_all()
    
    return success

def current_user() -> Any | None:
    user = session.get("user")
    if user == "admin":
        return "admin"
    # Prüfen, ob der User in den Personen existiert
    if any(p["name"] == user for p in current_state["persons"]):
        return user
    return None

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
        
        # Check Admin
        if username == "admin" and password == USERS["admin"]["password"]:
            session.permanent = True
            session["user"] = "admin"
            nxt = request.args.get("next")
            return redirect(nxt or url_for("render_index"))
        
        # Check reguläre User in current_state
        user_found = next((p for p in current_state["persons"] if p["name"] == username), None)
        if user_found and user_found.get("password") == password:
            session.permanent = True
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
    
    # Sicherstellen, dass die Person existiert (z.B. admin ist kein Teil von current_state["persons"])
    user_score = person["score"] if person else 0.0
    
    # 24h Vote Counts für das Initial-Rendering (Template)
    recent_ups = 0
    recent_downs = 0
    photo = None
    user_ranking_category = 11 # Default
    if person and person.get("id"):
        recent_ups, recent_downs = get_recent_vote_counts(person["id"])
        photo = person.get("photo")
        # Ranking Kategorie ermitteln
        sorted_list = get_sorted_scorelist()
        user_ranking_category = get_ranking_category(person, sorted_list) or 11
    
    return render_template("index.html",
                           logged_in_user=user,
                           display_name="Admin" if user == "admin" else user,
                           user_score=user_score,
                           user_ranking_category=user_ranking_category,
                           recent_ups=recent_ups,
                           recent_downs=recent_downs,
                           photo=photo)

def get_current_person():
    global current_state

    if current_user() == "admin":
        return {"id": -10, "name": "admin", "score": 0.0, "privileges": []}

    current_person = None

    for person in current_state["persons"]:
        if person["name"] == current_user():
            current_person = person

    return current_person

def get_structured_vote_log(vote_log, all_logs=False):
    flat_list = []

    # 1. Struktur auflösen (Flatten)
    if all_logs:
        # Für Admin: Alle Logs aller Personen sammeln
        for target_person_id, person_logs in vote_log.items():
            for voter_name, actions in person_logs.items():
                for action_type, details in actions.items():
                    flat_entry = {
                        "person": voter_name,
                        "target": next((p["name"] for p in current_state["persons"] if str(p["id"]) == target_person_id), target_person_id),
                        "operation": action_type,
                        "timestamp": details["timestamp"],
                        "comment": details["comment"]
                    }
                    if flat_entry["comment"] != "null":
                        flat_list.append(flat_entry)
    else:
        # Für normale User: Nur eigene Logs
        for voter_name, actions in vote_log.items():
            for action_type, details in actions.items():
                flat_entry = {
                    "person": voter_name,
                    "operation": action_type,
                    "timestamp": details["timestamp"],
                    "comment": details["comment"]
                }
                if flat_entry["comment"] != "null":
                    flat_list.append(flat_entry)

    # 2. Sortieren nach Timestamp (neueste zuerst)
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

    # Über jede Person (Key) im Log iterieren
    for person in vote_log:
        flat_list = []
        for votedBy in vote_log[person]:
            for vote in vote_log[person][votedBy]:
                flat_entry = {
                    "person": votedBy,
                    "operation": vote,
                    "timestamp": vote_log[person][votedBy][vote]["timestamp"],
                    "comment": vote_log[person][votedBy][vote]["comment"]
                }
                # Votes, deren 24h abgelaufen sind und die keinen Kommentar haben, kann man weglassen
                timestamp_dt = convert_from_iso_zulu(flat_entry["timestamp"])
                delta = get_utc_now() - timestamp_dt
                if flat_entry["comment"] != "null" or delta <= VOTE_COOLDOWN_HOURS * 2:
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

            if operation not in new_person_vote_log[voter]:
                new_person_vote_log[voter][operation] = {}

            new_person_vote_log[voter][operation]["timestamp"] = entry["timestamp"]
            new_person_vote_log[voter][operation]["comment"] = entry["comment"]

        # Den aktualisierten State zurückschreiben
        current_state["vote_log"][person] = new_person_vote_log

def get_recent_vote_counts(person_id: int):
    global current_state
    now = get_utc_now()
    cutoff = now - timedelta(hours=24)
    
    ups = 0
    downs = 0
    
    vote_log = current_state.get("vote_log", {})
    person_log = vote_log.get(str(person_id), {})
    
    for voter, actions in person_log.items():
        for action, details in actions.items():
            try:
                ts = convert_from_iso_zulu(details["timestamp"])
                if ts >= cutoff:
                    if action == "inc":
                        ups += 1
                    elif action == "dec":
                        downs += 1
            except Exception:
                continue
    return ups, downs

def get_safe_persons():
    global current_state
    safe_persons = []
    for p in current_state["persons"]:
        cp = p.copy()
        cp.pop("password", None)
        safe_persons.append(cp)
    return safe_persons

@app.route("/api/persons", methods=["GET"])
def get_persons() -> tuple[Response, int] | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return not_logged

    own_id = get_current_person()["id"]
    cooldowns = get_current_cooldowns()
    plus_cooldowns = cooldowns[0]
    minus_cooldowns = cooldowns[1]

    add_ranking_category_to_state(current_state)

    # Füge 24h Vote Counts hinzu
    for person in current_state["persons"]:
        ups, downs = get_recent_vote_counts(person["id"])
        person["recent_ups"] = ups
        person["recent_downs"] = downs

    with state_lock:
        if current_user() == "admin":
            logs = get_structured_vote_log(current_state["vote_log"], all_logs=True)
        else:
            logs = get_structured_vote_log(current_state["vote_log"].get(str(own_id), {}))

        return jsonify({"version": update_version, "persons": get_safe_persons(), "plusCooldowns": plus_cooldowns,
                        "minusCooldowns": minus_cooldowns,
                        "own_vote_log": logs})

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
    if delta >= VOTE_COOLDOWN_HOURS:
        return True
    else:
        return False

def record_vote(user: str, person_id: int, operation: str, comment: str) -> None:
    """
    Vote im Log vermerken (Zeitpunkt + Operation).
    Muss unter state_lock aufgerufen werden.
    """
    global current_state

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
        return jsonify({}), 401

    # Nicht für eigene Person voten
    if person_id == get_current_person()['id']:
        return jsonify({"error": "Es kann nicht für die eigene Person abgestimmt werden."}), 428

    user = current_user()

    with state_lock:
        current_person = get_current_person()
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
        
        # Unmittelbar Counts aktualisieren für die Response
        ups, downs = get_recent_vote_counts(person_id)
        person["recent_ups"] = ups
        person["recent_downs"] = downs

        if not bump_version():
            return jsonify({"error": "Konflikt beim Speichern. Bitte lade die Seite neu."}), 409
        return jsonify({"version": update_version, "person": person})

@app.route("/api/persons/<int:person_id>/dec", methods=["POST"])
def decrease_score(person_id: int) -> tuple[Response, int] | tuple[Response, int] | bool | Response:
    global current_state

    not_logged = ensure_logged_in_api()
    if not_logged:
        return jsonify({}), 401

    # Nicht für eigene Person voten
    if person_id == get_current_person()['id']:
        return jsonify({"error": "Es kann nicht für die eigene Person abgestimmt werden."}), 428

    user = current_user()

    with state_lock:
        current_person = get_current_person()
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

        # Unmittelbar Counts aktualisieren für die Response
        ups, downs = get_recent_vote_counts(person_id)
        person["recent_ups"] = ups
        person["recent_downs"] = downs

        if not bump_version():
            return jsonify({"error": "Fehler - Konflikt beim Speichern. Bitte lade die Seite neu."}), 409
        return jsonify({"version": update_version, "person": person})

@app.route("/api/user/photo", methods=["POST"])
def update_photo():
    not_logged = ensure_logged_in_api()
    if not_logged:
        return jsonify({}), 401

    photo_data = request.form.get("photo") # Base64 string
    if not photo_data:
        return jsonify({"error": "Kein Bild empfangen"}), 400

    # Maximale Größe prüfen (grobe Schätzung für Base64)
    # Gists haben ein Limit von ca. 1MB pro Datei.
    # Bei 150x150 JPEG (0.6 Qual) ist ein Bild ca. 10-20 KB groß.
    # 12 User * 20 KB = 240 KB. Das passt locker in das 1MB Gist.
    if len(photo_data) > 100000: # ca 100KB Limit pro Foto im Backend
        return jsonify({"error": "Bild ist zu groß"}), 413

    with state_lock:
        current_person = get_current_person()
        if not current_person or current_person["name"] == "admin":
            return jsonify({"error": "Nicht erlaubt"}), 403

        # Person im State finden
        person = next((p for p in current_state["persons"] if p["id"] == current_person["id"]), None)
        if not person:
            return jsonify({"error": "Person nicht gefunden"}), 404

        person["photo"] = photo_data

        if not bump_version():
            return jsonify({"error": "Fehler beim Speichern des Fotos."}), 409

        return jsonify({"success": True, "photo": photo_data})

@app.route("/api/diary", methods=["POST"])
def add_diary_entry():
    not_logged = ensure_logged_in_api()
    if not_logged:
        return jsonify({}), 401

    user_name = current_user()
    text = (request.form.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Tagebucheintrag darf nicht leer sein"}), 400
    if len(text) > 500:
        return jsonify({"error": "Tagebucheintrag ist zu lang (max. 500 Zeichen)"}), 400

    timestamp = convert_to_iso_zulu(get_utc_now())

    with diary_lock:

        diary_data = get_diary_data()
        if diary_data is None:
            return jsonify({"error": "Fehler - Tagebuch auf Server nicht gefunden"}), 404

        if not isinstance(diary_data, list):
            diary_data = []

        diary_data.append({"name": user_name, "timestamp": timestamp, "text": text})

        payload = {
            "files": {
                DIARY_FILENAME: {
                    "content": json.dumps(diary_data, indent=4)
                }
            }
        }
        response = requests.patch(f"https://api.github.com/gists/{os.environ.get('DIARY')}",
                                  headers=GIST_HEADERS,
                                  json=payload)
        if response.status_code != 200:
            return jsonify({"error": f"Fehler beim Speichern des Tagebuches: {response.text}"}), 409
        else:
            return jsonify({"success": True}), 200

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

    own_id = get_current_person()["id"]
#
    with version_condition:
        if update_version <= since:
            version_condition.wait(timeout=25.0)

        changed = update_version > since

        cooldowns = get_current_cooldowns()
        plus_cooldowns = cooldowns[0]
        minus_cooldowns = cooldowns[1]

        add_ranking_category_to_state(current_state)

        # Füge 24h Vote Counts hinzu
        for person in current_state["persons"]:
            ups, downs = get_recent_vote_counts(person["id"])
            person["recent_ups"] = ups
            person["recent_downs"] = downs

        if current_user() == "admin":
            logs = get_structured_vote_log(current_state["vote_log"], all_logs=True)
        else:
            logs = get_structured_vote_log(current_state["vote_log"].get(str(own_id), {}))

        return jsonify({"changed": changed, "version": update_version, "persons": get_safe_persons(),
                        "plusCooldowns": plus_cooldowns, "minusCooldowns": minus_cooldowns,
                        "own_vote_log": logs}), 200

@app.route("/api/admin/users/add", methods=["POST"])
def add_user():
    if current_user() != "admin":
        return jsonify({"error": "Nicht autorisiert"}), 403
    
    name = (request.form.get("name") or "").strip()
    password = (request.form.get("password") or "").strip()
    
    if not name or not password:
        return jsonify({"error": "Name und Passwort erforderlich"}), 400
    
    with state_lock:
        if any(p["name"] == name for p in current_state["persons"]):
            return jsonify({"error": "Benutzer existiert bereits"}), 400
        
        new_id = max((p["id"] for p in current_state["persons"]), default=0) + 1
        new_person = {
            "id": new_id,
            "name": name,
            "password": password,
            "photo": None,
            "score": STARTING_SCORE
        }
        current_state["persons"].append(new_person)
        if not bump_version():
            return jsonify({"error": "Fehler beim Speichern"}), 500
            
    return jsonify({"success": True, "person": {"id": new_id, "name": name, "score": STARTING_SCORE}})

@app.route("/api/admin/users/<int:person_id>", methods=["DELETE"])
def delete_user(person_id):
    if current_user() != "admin":
        return jsonify({"error": "Nicht autorisiert"}), 403
    
    with state_lock:
        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Benutzer nicht gefunden"}), 404
        
        current_state["persons"] = [p for p in current_state["persons"] if p["id"] != person_id]
        if not bump_version():
            return jsonify({"error": "Fehler beim Speichern"}), 500
            
    return jsonify({"success": True})

@app.route("/api/admin/users/update", methods=["POST"])
def update_user():
    if current_user() != "admin":
        return jsonify({"error": "Nicht autorisiert"}), 403
    
    person_id = request.form.get("id")
    new_name = request.form.get("name")
    new_password = request.form.get("password")
    
    if not person_id:
        return jsonify({"error": "ID erforderlich"}), 400
    
    try:
        person_id = int(person_id)
    except ValueError:
        return jsonify({"error": "Ungültige ID"}), 400

    with state_lock:
        person = next((p for p in current_state["persons"] if p["id"] == person_id), None)
        if not person:
            return jsonify({"error": "Benutzer nicht gefunden"}), 404
        
        if new_name is not None:
            new_name = new_name.strip()
            if not new_name:
                return jsonify({"error": "Name darf nicht leer sein"}), 400
            # Prüfen ob der neue Name bereits von einem ANDEREN Benutzer verwendet wird
            if any(p["name"] == new_name and p["id"] != person_id for p in current_state["persons"]):
                return jsonify({"error": "Benutzername bereits vergeben"}), 400
            person["name"] = new_name

        if new_password is not None:
            new_password = new_password.strip()
            if not new_password:
                return jsonify({"error": "Passwort darf nicht leer sein"}), 400
            person["password"] = new_password
        
        if new_name is None and new_password is None:
            return jsonify({"error": "Keine Änderungen angegeben"}), 400

        if not bump_version():
            return jsonify({"error": "Fehler beim Speichern"}), 500
            
    return jsonify({"success": True})

@app.route("/api/user/change_password", methods=["POST"])
def change_password():
    user = current_user()
    if not user:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    
    new_password = (request.form.get("password") or "").strip()
    if not new_password:
        return jsonify({"error": "Neues Passwort erforderlich"}), 400
    
    if user == "admin":
        return jsonify({"error": "Admin-Passwort kann hier nicht geändert werden"}), 403

    with state_lock:
        person = next((p for p in current_state["persons"] if p["name"] == user), None)
        if not person:
            return jsonify({"error": "Benutzer nicht gefunden"}), 404
        
        person["password"] = new_password
        
        if not bump_version():
            return jsonify({"error": "Fehler beim Speichern"}), 500
            
    return jsonify({"success": True})

@app.route("/api/admin/diary/pdf", methods=["GET"])
def download_diary_pdf():
    if current_user() != "admin":
        return jsonify({"error": "Nicht autorisiert"}), 403

    with diary_lock:
        diary_data = get_diary_data()

    if diary_data is None:
        return jsonify({"error": "Keine Daten gefunden"}), 404

    # PDF erstellen
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Experiment-Tagebuch (Gesamt)", ln=True, align="C")
    pdf.ln(10)

    for entry in diary_data:
        name = entry.get("name", "Unbekannt")
        ts = entry.get("timestamp", "")
        text = entry.get("text", "")

        # Formatierung für den PDF-Export
        try:
            dt = convert_from_iso_zulu(ts).strftime("%d.%m.%Y, %H:%M:%S")
        except Exception:
            dt = ts

        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 8, f"{name} - {dt}", ln=True)
        
        pdf.set_font("helvetica", "", 12)
        # Multi_cell für längere Texte
        pdf.multi_cell(0, 8, text)
        pdf.ln(5)
        # Trennlinie
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(5)

    # PDF in Buffer speichern
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output()
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"diary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

# Globaler Zustand im Speicher
current_state = load_current_state()

if __name__ == "__main__":
    # Debug nur lokal; für Produktion WSGI-Server nutzen
    app.run(debug=True, threaded=True)