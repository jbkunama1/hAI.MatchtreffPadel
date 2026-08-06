![Matchtreff Padel Banner](Logo_II_Banner.png)

# hAI.MatchtreffPadel - Padel Matchtreff Anmeldung

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![GitHub stars](https://img.shields.io/github/stars/jbkunama1/hAI.MatchtreffPadel)](https://github.com/jbkunama1/hAI.MatchtreffPadel)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Docker ready](https://img.shields.io/badge/docker-ready-blue)
![Backend: Flask](https://img.shields.io/badge/Backend-Flask-blue)
![SQLite](https://img.shields.io/badge/Database-SQLite-07405E)
![Telegram Bot](https://img.shields.io/badge/Bot-Telegram-26A5E4)

Flask-Webapp **und Telegram-Bot** mit gemeinsamem SQLite-Backend fuer den woechentlichen Padel-Matchtreff am Donnerstag. Die Anwendung ist fuer eine einfache Anmeldung ohne Spieler-Login ausgelegt und bietet gleichzeitig Admin-Steuerung, Warteliste, Automatik und Benachrichtigungen.

## Uebersicht

- Einfache Anmeldung nur mit Namen.
- Zwei feste Donnerstag-Slots: `18:00 - 20:00` und `20:00 - 22:00`.
- Gemeinsames SQLite-Backend fuer Web-App, Bot und Scheduler.
- Admin-Dashboard fuer Limits, Bearbeitung, Reset, Themes und Backups.
- Telegram-Bot fuer Anmeldung, Uebersicht und Admin-Kommandos.
- Docker-/Compose-Setup fuer Deployment, z. B. ueber Portainer.

## Features

### Spieler

- Anmeldung ohne Account oder Passwort.
- Eintragung fuer einen oder beide Slots.
- Live-Anzeige freier Plaetze.
- Automatische Warteliste bei vollen Slots.
- Mitglied/Gast-Unterscheidung ueber Checkbox.
- Schutz vor Doppelanmeldungen.
- Die Anmeldung kann von einem Admin gesperrt werden; dann ist die Eintragung nur noch fuer Admins moeglich.

### Admins

- Passwortgeschuetzter Login unter `/admin/login`.
- Maximale Teilnehmerzahl pro Slot anpassen.
- Eintraege loeschen und bearbeiten.
- Alle Anmeldungen fuer die kommende Woche zuruecksetzen.
- Datenbank-Backup herunterladen.
- Automatik fuer Reset, Digest und Teilnehmer-Reminder konfigurieren (Tab "⚙️ Automatik").
- Themes, Hintergrundbilder und Hintergrundeffekte umschalten.
- Weitere Admins anlegen oder entfernen.
- **Anmeldesperre** verwalten (Tab "🔒 Anmeldung"): Anmeldung fuer normale Nutzer manuell oeffnen oder sperren, oder eine automatische Freigabe zu einem festen Datum/Uhrzeit planen. Admins koennen sich immer eintragen.

### Anmeldesperre

Die Anmeldung ist fuer normale Nutzer standardmaessig **geschlossen**. Sie wird nur freigeschaltet, wenn ein **Admin** sie oeffnet (manuell oder automatisch zu einer geplanten Uhrzeit). Darueber hinaus:

- Ab Donnerstag 22 Uhr bleibt die Anmeldung fuer normale Nutzer gesperrt, bis ein Admin sie wieder freigibt.
- **Admins koennen sich immer eintragen**, unabhaengig vom Sperr-Status.
- Der woechentliche Reset setzt die Sperre wieder auf den Standard (geschlossen) zurueck.
- Auf der Startseite erscheint ein **Hinweistext**, ab wann die Liste oeffnet: Standard ist der **naechste Dienstag um 13:00 Uhr**. Hat ein Admin eine automatische Freigabe hinterlegt, wird stattdessen dieser Zeitpunkt angezeigt (mitsamt Datum). Bei manueller Freigabe heisst es "Die Liste ist gerade geoeffnet."

### Telegram

Der Bot arbeitet komplett mit **Inline-Buttons** und kennt zwei Rollen:

- **Enduser**: Chat-basierte Anmeldung, eigener Status, Nachricht an den Admin.
- **Admin**: alle Admin-Funktionen (Liste, Loeschen, Max-Limit, Reset, CSV-Export, Einstellungen, Broadcast).

Start mit `/start`, alle weiteren Aktionen laufen ueber Inline-Buttons. `Gäste` (nicht-Mitglieder) erhalten sofort einen Eintrag; die Admins werden per Benachrichtigung informiert und koennen per Inline-Button bestaetigen oder entfernen.

## Aktueller Funktionsstand

- **Bestätigte Anmeldungen:** Anmeldungen, die von einem Admin offiziell bestätigt wurden, erhalten auf der öffentlichen Liste eine grüne Kennzeichnung.
- **Kommentarfeld:** Nutzer können nun Kommentare unter der Liste hinterlassen.
- **Download-Bereich:** Admins können Dateien (z. B. Bilder oder APKs) für alle Nutzer zum Download bereitstellen.
- **Chat/Hilfe-System:** Internes Nachrichtensystem, um Admins direkt zu kontaktieren, ergänzt um ein FAQ-Modul.
- **Domain-Übersicht:** Auflistung aller Domains auf der Über-uns-Seite.
- **Padel Americana Ad:** Werbung für die App auf der Über-uns-Seite.
- **Warteliste-Modi:** Admins können entscheiden, ob eine Bestätigung den Nutzer auf der Warteliste belässt oder direkt auf die Liste befördert.

## Slots

| Slot | Zeitraum |
|---|---|
| Slot A | 18:00 - 20:00 Uhr |
| Slot B | 20:00 - 22:00 Uhr |

Spieler koennen sich fuer einen oder beide Slots eintragen. Ist ein Slot voll, wird die Anmeldung auf die Warteliste gesetzt, solange dort noch Plaetze verfuegbar sind.

## Tech-Stack

| Bereich | Technologie |
|---|---|
| Backend | Python, Flask, Gunicorn |
| Datenbank | SQLite |
| Bot | python-telegram-bot |
| Scheduler | APScheduler |
| Frontend | HTML, CSS, responsive Eigenentwicklung |
| Deployment | Docker, Docker Compose, Portainer |

## Projektstruktur

```text
.
├── app.py
├── telegram_bot.py
├── scheduler.py
├── scheduler_new.py       # Job-Kern: Reset, Digest, Reminder
├── index.html
├── templates/
├── static/
│   └── pictures/          # Hintergrundbilder fuer die Galerie
├── .github/
│   └── workflows/
│       └── docker-build-push.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── env.example
```

## Setup

### Lokal starten

Voraussetzungen: Python 3.11+

```bash
git clone https://github.com/jbkunama1/hAI.MatchtreffPadel.git
cd hAI.MatchtreffPadel
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

```bash
export SECRET_KEY="change-me"
export ADMIN_PASSWORD_ADMIN="change-me"
export ADMIN_PASSWORD_DANIEL="change-me"
export PORT="1905"
python app.py
```

Danach ist die Web-App unter `http://localhost:1905` erreichbar.

### Telegram-Bot starten

```bash
export TELEGRAM_BOT_TOKEN="dein-bot-token"
export ADMIN_TELEGRAM_IDS="123456789,987654321"
# optional: Admin-Verify-Code, mit dem sich weitere Admins im Bot verifizieren koennen
export TELEGRAM_ADMIN_VERIFY_CODE="geheimer-code"
python telegram_bot.py
```

#### Rollen im Bot

| Rolle | Rechte |
|---|---|
| **Enduser** | Chat-Anmeldung (Name → Mitglied/Gast → Slot-Auswahl), Status abfragen, Nachricht an Admin senden |
| **Admin** | Liste, Nutzer loeschen, Max. Spieler setzen, Reset, CSV-Export, Einstellungen (Wartelisten-Modus, Slot-Auswahl), Broadcast an alle Nutzer |

Die Admin-Rolle wird ueber `ADMIN_TELEGRAM_IDS` (Komma-getrennte Telegram-IDs) vergeben. Alternativ kann sich ein Nutzer mit `TELEGRAM_ADMIN_VERIFY_CODE` selbst zum Admin verifizieren. Die Rollen werden in der Tabelle `telegram_users` gespeichert.

### Automatik / Scheduler

Der Scheduler (`scheduler.py` + `scheduler_new.py`) laeuft als eigener Container und erledigt automatisiert drei Aufgaben:

- **Woechlicher Reset**: Leert alle Anmeldungen (z. B. Freitag frueh 06:00 Uhr) fuer die kommende Woche. Wochentag, Uhrzeit und Aktivierung sind einstellbar.
- **Digest**: Fasst regulaer (Standard alle 60 Minuten) neue Anmeldungen zusammen und schickt sie an alle Admins (`ADMIN_TELEGRAM_IDS`).
- **Teilnehmer-Reminder**: Erinnert angemeldete Spieler an den Spieltag und schickt den Admins eine Belegungs-Statusmeldung.

Alle Einstellungen werden im Admin-Dashboard unter **⚙️ Automatik** gespeichert. Der Scheduler liest die Konfiguration bei jedem Durchlauf frisch aus der Datenbank (kein Neustart noetig).

### Kurzfassung fuer Assets

Die Medien und Bilder liegen im Repo bereits an den richtigen Stellen:

- `static/Logo_I_Matchtreff.png`: kleines Logo fuer den Header.
- `static/Logo_II_Banner.png`: Banner fuer Landingpage und README.
- `static/Matchtreff_Silber.mp4`: Erklaervideo.
- `static/pictures/`: alle Bilder fuer die Admin-Galerie (eigenes Hintergrundbild).

## Docker & Portainer

### Docker Compose

```bash
docker compose up -d
# oder: docker-compose up -d
```

Der Stack umfasst drei Services:

- `matchtreff_web`
- `matchtreff_bot`
- `matchtreff_scheduler`

Alle drei Container teilen sich das Volume `matchtreff_data` und damit dieselbe SQLite-Datenbank.

### Deployment ueber Portainer

Es gibt zwei gleichwertige Wege: **Stack aus dem Git-Repository selbst bauen** (Methode A) oder **das fertige GHCR-Image ziehen** (Methode B, empfohlen — schneller, kein Build im Portainer noetig).

#### Methode A: Git-basierter Stack (Build aus dem Repository)

1. In Portainer **Stacks** oeffnen.
2. **Add stack** waehlen.
3. Als Build-Methode **Repository** auswaehlen.
4. Repo `https://github.com/jbkunama1/hAI.MatchtreffPadel` und `docker-compose.yml` eintragen.
5. `SECRET_KEY`, `ADMIN_PASSWORD_*`, `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_IDS` und optional `LOG_LEVEL` (INFO/DEBUG/WARNING/ERROR) als Umgebungsvariablen setzen.
6. Stack deployen oder spaeter per GitOps / Pull and redeploy aktualisieren.

#### Methode B: Git-Stack mit fertigem GHCR-Image (empfohlen, kein Build)

Das Image ist bereits fertig gebaut und liegt in der GitHub Container Registry (`ghcr.io/jbkunama1/hai.matchtreffpadel:latest`). Im Repo gibt es dafuer eine eigene Compose-Datei **ohne `build:`** — Portainer holt sich diese Datei und startet das fertige Image einfach:

1. In Portainer **Stacks** oeffnen.
2. **Add stack** waehlen.
3. Als Build-Methode **Repository** auswaehlen.
4. Repo `https://github.com/jbkunama1/hAI.MatchtreffPadel` und **Compose path `ghcr-docker-compose.yml`** eintragen (Reference `refs/heads/main`).
5. `SECRET_KEY`, `ADMIN_PASSWORD_*`, `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_IDS` und optional `LOG_LEVEL` (INFO/DEBUG/WARNING/ERROR) als Umgebungsvariablen setzen.
6. **Deploy the stack** klicken. Portainer zieht das fertige Image automatisch (kein Build).
7. Um zu aktualisieren: Stack waehlen, dann **Actions → Pull and redeploy** (holt dann auch das neueste Image).

### Docker-Image ueber GitHub Actions (GHCR)

Ein GitHub-Actions-Workflow (`.github/workflows/docker-build-push.yml`) baut bei jedem Push auf `main` automatisch ein Docker-Image und pusht es nach `ghcr.io/jbkunama1/hai.matchtreffpadel`. Der Build kann auch manuell ausgeloest werden:

1. Auf GitHub den Tab **Actions** oeffnen.
2. Links den Workflow **Docker Build and Push to GHCR** waehlen.
3. Auf **Run workflow** klicken (optional Branch waehlen).

Das Image wird mit den Tags `latest` (nur bei Default-Branch) und ggf. Branch-/SemVer-Tags versehen. Nach dem ersten Push muss die Sichtbarkeit des GHCR-Pakets ggf. auf **public** gesetzt werden, damit der Portainer-Stack das Image ohne Login ziehen kann.

## Admin-Verwaltung

Beim ersten Start werden initiale Admins ueber Umgebungsvariablen angelegt. Die Passwoerter werden sicher gehasht gespeichert.

| Benutzername | Passwort-Variable |
|---|---|
| `Admin` | `ADMIN_PASSWORD_ADMIN` |
| `Daniel` | `ADMIN_PASSWORD_DANIEL` |
| `Cosme` | `ADMIN_PASSWORD_COSME` |
| `Sascha` | `ADMIN_PASSWORD_SASCHA` |
| `Patrick` | `ADMIN_PASSWORD_PATRICK` |

Weitere Admins lassen sich spaeter im Bereich `/admin/users` anlegen. Der letzte verbleibende Admin kann nicht geloescht werden, und ein Admin kann sich nicht selbst entfernen.

## Warteliste und Schutzmechanismen

- Pro Slot ist ein normalisierter Name nur einmal erlaubt.
- Im Web wird zusaetzlich pro Slot ein Cookie gesetzt.
- Im Telegram-Bot verhindert die User-ID eine zweite Anmeldung fuer denselben Slot.
- Die Warteliste ist pro Slot auf `4` Eintraege begrenzt.
- Wird ein Platz frei oder das Limit erhoeht, ruecken Wartelisten-Eintraege automatisch nach.

## Design und UI

- Responsives Layout fuer Desktop, Tablet und Smartphone.
- Touch-freundliche Bedienelemente auf mobilen Geraeten.
- Themes mit Farbverlaeufen oder eigenen Hintergrundbildern.
- Dunkles Theme als Standard moeglich.
- Schwebender Hintergrundeffekt mit Blasen oder Padel-Ball-Icons.
- Banner auf groesseren Displays und vergroessertes Logo im Header.

## Logos, Medien und Branding

- `static/Logo_I_Matchtreff.png`: kleines Logo fuer den Header.
- `static/Logo_II_Banner.png`: Banner fuer Landingpage und README.
- `static/Matchtreff_Silber.mp4`: Erklaervideo fuer Landingpage und Info-Seite.

## Sicherheit und Betrieb

- In Produktion immer einen starken `SECRET_KEY` verwenden.
- Alle `ADMIN_PASSWORD_*`-Werte durch sichere Passwoerter ersetzen.
- `TELEGRAM_BOT_TOKEN` niemals als Platzhalter belassen.
- Deployment moeglich hinter Reverse Proxy wie nginx, Traefik oder Cloudflare Tunnel.
- Das Volume `matchtreff_data` regelmaessig sichern.
- Alternativ kann der Backup-Button im Admin-Dashboard genutzt werden.

## Troubleshooting

### Scheduler-Container startet nicht / macht nichts

Der Scheduler benoetigt die Pakete `APScheduler` und `tzdata` (in `requirements.txt`). Falls der Container mit `ModuleNotFoundError` startet, das Image neu bauen (`docker compose build scheduler` bzw. Stack neu deployen). Ausserdem sicherstellen, dass `MATCHTREFF_DB_PATH` im Compose auf dasselbe Volume zeigt wie die Web-App, damit Scheduler und App dieselbe Datenbank nutzen.

### Portainer-Variablen werden ignoriert

Falls ein Container trotz gesetzter Werte mit `change-me` startet, pruefen, ob in `docker-compose.yml` ueberall `${VARIABLE_NAME}` statt harter Platzhalter verwendet wird. Nach Anpassungen den Stack neu deployen.

### Gunicorn WORKER TIMEOUT

Bei Timeouts helfen die bereits vorgesehenen Massnahmen im Projekt:

- SQLite im WAL-Modus.
- `busy_timeout` fuer konkurrierende Zugriffe.
- Mehrere Gunicorn-Worker und Threads.
- Gemeinsames korrekt gemountetes `instance/`-Volume fuer alle Container.

## Admin-Funktionen im Vergleich

| Funktion | Web-App | Telegram-Bot |
|---|---|---|
| Slot-Belegung ansehen | Startseite | `/start` → Belegung anzeigen |
| Anmelden | Formular mit Name + Slot-Auswahl (+ optionaler Loesch-PIN) | `/start` → "Anmelden" → Inline-Buttons |
| Eintrag bearbeiten | Admin-Dashboard | - |
| Max. Plaetze setzen | Admin-Dashboard | Admin-Menue → "Max. Spieler setzen" |
| Anmeldung loeschen | Admin-Dashboard oder Stornier-Seite mit Loesch-PIN | Admin-Menue → "Nutzer loeschen" |
| Reset | Admin-Dashboard | Admin-Menue → "Alle Anmeldungen zuruecksetzen" |
| CSV-Export | Backup herunterladen | Admin-Menue → "Export (CSV)" |
| Broadcast | - | Admin-Menue → "Broadcast an alle Nutzer" |
| Automatik konfigurieren | Admin-Dashboard | - |

## Lizenz

MIT License - siehe `LICENSE`.
