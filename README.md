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

## Docker

Ein `Dockerfile` ist vorhanden. Die Umgebungsvariablen müssen beim Start des Containers mitgegeben werden.

```bash
docker build -t social-scoring .
docker run -p 5000:5000 \
  -e GITHUB_TOKEN=your_token \
  -e GIST_ID=your_id \
  -e SECRET_KEY=your_secret \
  social-scoring
```
