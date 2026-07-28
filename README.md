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

### Admins

- Passwortgeschuetzter Login unter `/admin/login`.
- Maximale Teilnehmerzahl pro Slot anpassen.
- Eintraege loeschen und bearbeiten.
- Alle Anmeldungen fuer die kommende Woche zuruecksetzen.
- Datenbank-Backup herunterladen.
- Automatik fuer Reset und Digest konfigurieren.
- Themes, Hintergrundbilder und Hintergrundeffekte umschalten.
- Weitere Admins anlegen oder entfernen.

### Telegram

- `/slots` fuer aktuelle Belegung.
- `/eintragen <Name> <a|b|beide>` fuer Anmeldungen.
- `/status <Name>` fuer den eigenen Status.
- Admin-Kommandos wie `/admin_liste`, `/admin_max`, `/admin_loeschen`, `/admin_reset`.
- Sofort-Benachrichtigung an Admins bei Gast-Anmeldungen mit Inline-Buttons.

## Aktueller Funktionsstand

- **Kein Pending-Status mehr:** Mitglied- und Gast-Anmeldungen werden sofort eingetragen.
- **Gast-Benachrichtigung per Telegram:** Admins erhalten bei Gast-Anmeldungen direkte Hinweise.
- **Bildergalerie im Admin-Panel:** Bilder aus `pictures/` koennen als Hintergrund uebernommen werden.
- **Groessere Hintergrund-Icons:** Padel-Ball-Icons wurden deutlich vergroessert.
- **Automatisches Donnerstagsdatum:** `{next_thursday}` wird bei Seitenaufruf dynamisch ersetzt.
- **Warteliste mit Auto-Nachruecken:** Freie Plaetze werden automatisch aufgefuellt.
- **Dark Mode / Theme-Steuerung:** Einstellungen gelten global fuer alle Besucher.

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
├── index.html
├── templates/
├── static/
├── pictures/
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
python telegram_bot.py
```

### Kurzfassung fuer Assets

Einige Dateien muessen fuer die Flask-Auslieferung im `static/`-Ordner liegen:

```bash
cp Logo_I_Matchtreff.png static/Logo_I_Matchtreff.png
cp Matchtreff_Silber.mp4 static/Matchtreff_Silber.mp4
mkdir -p static/backgrounds static/pictures
```

Falls Bild-Themes oder die Galerie genutzt werden, muessen die benoetigten Bilder aus `pictures/` in die passenden `static/`-Unterordner kopiert werden.

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

1. In Portainer **Stacks** oeffnen.
2. **Add stack** waehlen.
3. Als Build-Methode **Repository** auswaehlen.
4. Repo `https://github.com/jbkunama1/hAI.MatchtreffPadel` und `docker-compose.yml` eintragen.
5. `SECRET_KEY`, `ADMIN_PASSWORD_*`, `TELEGRAM_BOT_TOKEN` und `ADMIN_TELEGRAM_IDS` als Umgebungsvariablen setzen.
6. Stack deployen oder spaeter per GitOps / Pull and redeploy aktualisieren.

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

- `Logo_I_Matchtreff.png`: kleines Logo fuer den Header.
- `Logo_II_Banner.png`: Banner fuer Landingpage und README.
- `Matchtreff_Silber.mp4`: Erklaervideo fuer Landingpage und Info-Seite.

## Sicherheit und Betrieb

- In Produktion immer einen starken `SECRET_KEY` verwenden.
- Alle `ADMIN_PASSWORD_*`-Werte durch sichere Passwoerter ersetzen.
- `TELEGRAM_BOT_TOKEN` niemals als Platzhalter belassen.
- Deployment moeglich hinter Reverse Proxy wie nginx, Traefik oder Cloudflare Tunnel.
- Das Volume `matchtreff_data` regelmaessig sichern.
- Alternativ kann der Backup-Button im Admin-Dashboard genutzt werden.

## Troubleshooting

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
| Slot-Belegung ansehen | Startseite | `/slots`, `/admin_liste` |
| Anmelden | Formular mit Name + Slot-Auswahl | `/eintragen <Name> <a\|b\|beide>` |
| Eintrag bearbeiten | Admin-Dashboard | - |
| Max. Plaetze setzen | Admin-Dashboard | `/admin_max <a\|b> <zahl>` |
| Anmeldung loeschen | Admin-Dashboard | `/admin_loeschen <id>` |
| Reset | Admin-Dashboard | `/admin_reset` |
| Automatik konfigurieren | Admin-Dashboard | - |
| Backup herunterladen | Admin-Dashboard | - |

## Lizenz

MIT License - siehe `LICENSE`.
