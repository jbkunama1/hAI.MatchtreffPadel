# hAI.MatchtreffPadel - Padel Matchtreff Anmeldung

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![GitHub stars](https://img.shields.io/github/stars/jbkunama1/hAI.MatchtreffPadel)](https://github.com/jbkunama1/hAI.MatchtreffPadel)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Docker ready](https://img.shields.io/badge/docker-ready-blue)
![Backend: Flask](https://img.shields.io/badge/Backend-Flask-blue)

Flask-Webapp mit SQLite-Backend für den wöchentlichen Padel-Matchtreff am Donnerstag, inklusive einer kleinen Landing-Page (`index.html`). Lizenz: MIT (siehe `LICENSE`).

## Architektur

- **Web-App (Flask)**
  - Keine Benutzerverwaltung, keine Registrierung, kein Login für Spieler
  - Anmeldung ausschließlich über Namenseingabe für einen oder beide Donnerstag-Slots
  - Admin-Bereich passwortgeschützt über eine einzelne Umgebungsvariable (`ADMIN_PASSWORD`)
  - Läuft standardmäßig auf Port **1905**
- **SQLite-Datenbank**
  - Datei: `instance/matchtreff.sqlite3`
  - Tabellen:
    - `slots` (Slot-Key, Bezeichnung, maximale Teilnehmerzahl)
    - `signups` (Name, zugehöriger Slot, Zeitstempel)
- **Docker-/Portainer-Stack**
  - Ein Container für die Web-App
  - Volume für die Datenbank
- **Landing Page**
  - Statische `index.html` als Einstieg für das Projekt (Beschreibung, Links)

## Slots

| Slot | Zeitraum |
|---|---|
| Slot A | 18:00 - 20:00 Uhr |
| Slot B | 20:00 - 22:00 Uhr |

Spieler können sich für einen oder beide Slots eintragen. Ist ein Slot bereits voll, ist die Auswahl für diesen Slot deaktiviert.

## Features im Detail

- Anmeldung nur mit Namen - keine E-Mail-Adresse, kein Passwort, kein Account nötig
- Pro Slot eine vom Admin festgelegte maximale Teilnehmerzahl
- Live-Anzeige, wie viele Plätze pro Slot noch frei sind
- Admin-Bereich (passwortgeschützt):
  - Maximale Teilnehmerzahl pro Slot ändern
  - Einzelne Anmeldungen löschen
  - Alle Anmeldungen für die kommende Woche zurücksetzen
- Nur der Admin darf Anmeldungen ändern oder löschen - Spieler selbst können das nicht

## Lokale Installation (ohne Docker)

Voraussetzungen: Python 3.11+

```bash
git clone https://github.com/jbkunama1/hAI.MatchtreffPadel.git
cd hAI.MatchtreffPadel
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

### Web-App starten

```bash
export SECRET_KEY="change-me"        # in Produktion durch sicheren Key ersetzen
export ADMIN_PASSWORD="change-me"    # Passwort für den Admin-Bereich
export PORT="1905"                   # Port für die Web-App
python app.py
```

Danach im Browser: `http://localhost:1905`

## Docker / Portainer

### Image bauen

```bash
docker build -t haimatchtreffpadel:latest .
```

### Stack mit docker-compose

```bash
docker compose up -d
# oder: docker-compose up -d
```

`docker-compose.yml` definiert einen Service:

```yaml
services:
  matchtreff_padel:
    build: .
    container_name: matchtreff_padel
    ports:
      - "1905:1905"
    environment:
      - SECRET_KEY=change-me
      - ADMIN_PASSWORD=change-me
    volumes:
      - matchtreff_data:/app/instance
    restart: unless-stopped

volumes:
  matchtreff_data:
```

- Web-App: erreichbar auf Port 1905
- Datenbank: Volume `matchtreff_data` (enthält `instance/matchtreff.sqlite3`)

### Einsatz in Portainer

1. In Portainer unter **Stacks → Add stack** gehen.
2. Inhalt der `docker-compose.yml` einfügen.
3. Die Umgebungsvariablen `SECRET_KEY` und `ADMIN_PASSWORD` auf sichere Werte setzen.
4. Stack deployen.

## Sicherheit / Betrieb

- In Produktion immer einen starken `SECRET_KEY` und ein sicheres `ADMIN_PASSWORD` verwenden.
- Zugriff auf die Web-App über einen Reverse Proxy (nginx, Traefik, Cloudflare Tunnel) absichern.
- Volume `matchtreff_data` regelmäßig sichern (Backups).

## Admin-Funktionen

Der Admin loggt sich über `/admin/login` mit dem Passwort aus `ADMIN_PASSWORD` ein. Im Admin-Bereich stehen folgende Funktionen zur Verfügung:

- Überblick über beide Slots inkl. aktueller Belegung
- Maximale Teilnehmerzahl pro Slot direkt anpassen
- Einzelne Anmeldungen löschen (z. B. bei Absagen)
- Alle Anmeldungen zurücksetzen, um eine neue Woche zu starten

Spieler selbst haben **keine** Möglichkeit, ihre Anmeldung zu ändern oder zu löschen - dies liegt bewusst ausschließlich beim Admin.
