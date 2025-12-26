# Social Scoring Experiment

Dieses Projekt ist eine Web-Anwendung für ein soziales Experiment, bei dem Teilnehmer sich gegenseitig bewerten können. Basierend auf dem Score erhalten die Teilnehmer verschiedene Privilegien oder Einschränkungen.

## Features

- **Echtzeit-Updates:** Dank Long-Polling werden Änderungen sofort bei allen Teilnehmern angezeigt.
- **Ranking-System:** Automatisches Ranking basierend auf dem Score mit dynamischer Zuweisung von Privilegien.
- **Cooldown-System:** Verhindert Spamming durch eine Sperre (Default: 12 Stunden) nach jedem Vote.
- **Kommentar-Funktion:** Votes können optional mit anonymen Kommentaren versehen werden.
- **Admin-Panel:** Der Admin kann alle Votes und Kommentare einsehen.
- **Persistenz:** Daten werden in einem GitHub Gist gespeichert.

## Voraussetzungen

- Python 3.x
- Ein GitHub-Account und ein [Personal Access Token](https://github.com/settings/tokens) (mit `gist` Scope).
- Ein existierendes Gist (kann eine leere `score.json` enthalten).

## Setup

1. Repository klonen.
2. Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. Umgebungsvariablen setzen (z.B. in einer `.env` Datei oder direkt im System):
   - `GITHUB_TOKEN`: Dein GitHub Personal Access Token.
   - `GIST_ID`: Die ID deines Gists.
   - `SECRET_KEY`: Ein geheimer Schlüssel für Flask-Sessions.

4. Anwendung starten:
   ```bash
   python app.py
   ```

## Docker & Mehrere Instanzen

Die Anwendung ist vollständig containerisiert und kann leicht in mehreren separaten Instanzen (z.B. für verschiedene Klassen oder Gruppen) betrieben werden. Jede Instanz benötigt eigene GitHub Gists für die Datenhaltung.

### Einzelne Instanz starten
```bash
docker build -t social-scoring .
docker run -d -p 5000:5000 \
  -e GITHUB_TOKEN=your_token \
  -e GIST_ID=your_score_gist_id \
  -e DIARY=your_diary_gist_id \
  -e ADMIN_PASSWORD=your_admin_password \
  -e SECRET_KEY=your_secret \
  social-scoring
```

### Mehrere Instanzen (Docker Compose)
Um mehrere Instanzen parallel auf einem Server zu betreiben, nutze die bereitgestellte `docker-compose.yml`. Passe die Ports und Gist-IDs für jede Gruppe an:

```yaml
services:
  klasse-10a:
    build: .
    ports: ["5001:5000"]
    environment:
      - GITHUB_TOKEN=...
      - GIST_ID=gist_id_fuer_10a
      - DIARY=diary_id_fuer_10a
      - ADMIN_PASSWORD=geheim10a
      - SECRET_KEY=secret1
  
  klasse-10b:
    build: .
    ports: ["5002:5000"]
    environment:
      - GITHUB_TOKEN=...
      - GIST_ID=gist_id_fuer_10b
      - DIARY=diary_id_fuer_10b
      - ADMIN_PASSWORD=geheim10b
      - SECRET_KEY=secret2
```

Starte alle Instanzen mit:
```bash
docker-compose up -d
```

### Voraussetzungen für separate Instanzen
1. **GitHub Token:** Ein Token kann für alle Instanzen verwendet werden.
2. **Gists:** Erstelle für jede Gruppe zwei separate Gists (eins für die Scores, eins für das Tagebuch).
3. **Konfiguration:** Jede Instanz wird über Umgebungsvariablen isoliert (eigene User-Liste, eigener Admin, eigene Daten).
