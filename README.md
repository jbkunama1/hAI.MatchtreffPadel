![Matchtreff Padel Banner](Logo_II_Banner.png)

# hAI.MatchtreffPadel - Padel Matchtreff Anmeldung

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![GitHub stars](https://img.shields.io/github/stars/jbkunama1/hAI.MatchtreffPadel)](https://github.com/jbkunama1/hAI.MatchtreffPadel)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Docker ready](https://img.shields.io/badge/docker-ready-blue)
![Backend: Flask](https://img.shields.io/badge/Backend-Flask-blue)

Flask-Webapp **und Telegram-Bot** mit gemeinsamem SQLite-Backend fuer den woechentlichen Padel-Matchtreff am Donnerstag. Lizenz: MIT (siehe `LICENSE`).

## Logos & Branding

- `Logo_I_Matchtreff.png` (Root des Repos) - kleines Logo, wird im Header der Web-App angezeigt. Fuer die Flask-App muss die Datei zusaetzlich nach `static/Logo_I_Matchtreff.png` kopiert werden, da Flask statische Dateien nur aus `static/` ausliefert.
- `Logo_II_Banner.png` (Root des Repos) - grosses Banner, wird ganz oben auf der Landing-Page (`index.html`) sowie im Kopf dieser README angezeigt.

```bash
cp Logo_I_Matchtreff.png static/Logo_I_Matchtreff.png
```

## Projektueberblick

- Flask-Web-App ohne Login fuer Spieler - nur Name eintragen, fertig
- Zwei feste Donnerstag-Slots: `18:00 - 20:00` und `20:00 - 22:00`
- Admin legt maximale Teilnehmerzahl pro Slot fest
- Aenderungen und Loeschungen von Anmeldungen ausschliesslich durch den Admin
- **Telegram-Bot** zum Eintragen und als Admin-Steuerung, parallel zur Web-App
- SQLite-Backend im `instance/`-Ordner, von Web-App und Bot gemeinsam genutzt
- Docker-/Compose-Setup mit zwei Containern (Web & Bot) auf Port `1905`

## Tech-Stack

- **Backend:** Python, Flask, Gunicorn
- **Datenbank:** SQLite
- **Bot:** python-telegram-bot
- **UI:** eigenes responsives CSS im VfB-Kaessle-Design

## Slots

| Slot | Zeitraum |
|---|---|
| Slot A | 18:00 - 20:00 Uhr |
| Slot B | 20:00 - 22:00 Uhr |

Spieler koennen sich fuer einen oder beide Slots eintragen. Ist ein Slot bereits voll, ist die Auswahl fuer diesen Slot deaktiviert (Web) bzw. wird abgelehnt (Bot).

## UI-Details (wie bei VfBAHKaessle)

- **Hintergrund-Bubbles:** Wie im Original-Repo steigen dezente, animierte Blasen im Hintergrund auf (per CSS `@keyframes`, respektiert `prefers-reduced-motion`).
- **Vollstaendig responsive:** Eigene Breakpoints fuer Tablet (< 992px), Mobile (< 768px) und kleine Handys (< 480px) - Buttons werden auf dem Handy automatisch zu vollbreiten Touch-Zielen (min. 44px Hoehe), Checkboxen sind vergroessert, Schriftgroessen und Abstaende passen sich an.
- Gilt sowohl fuer die Flask-Web-App (`templates/base.html`) als auch fuer die Landing-Page (`index.html`).

## Design-Themes (wie bei PollUnit)

Der Admin kann im Admin-Dashboard zwischen mehreren vordefinierten Hintergruenden/Farbschemata waehlen, aehnlich den Themes bei PollUnit. Aktuell verfuegbar:

| Theme | Beschreibung |
|---|---|
| Standard (Blau) | Helles Blau/Grau, wie bisher |
| Sunset (Orange) | Warmer Orange-Verlauf |
| Court (Gruen) | Gruener Verlauf, passend zum Padel-Court |
| Night (Dunkel) | Dunkles Design fuer Abendmodus |

Das gewaehlte Theme wird in der Datenbank gespeichert (`settings`-Tabelle) und gilt fuer alle Besucher der Web-App, bis der Admin es aendert. Neue Themes lassen sich einfach im Dictionary `THEMES` in `app.py` ergaenzen (Label, Hintergrund-Verlauf, zwei Akzentfarben).


### Themes mit eigenen Hintergrundbildern

Zusaetzlich zu den Farbverlauf-Themes gibt es Themes, die eigene Hintergrundbilder aus dem `pictures/`-Verzeichnis nutzen (z. B. `Racketfire.png`, `Racketsplash.png`). Fuer die Web-App muessen diese Bilder zusaetzlich nach `static/backgrounds/` kopiert werden, da Flask statische Dateien nur aus `static/` ausliefert:

```bash
mkdir -p static/backgrounds
cp pictures/Racketfire.png static/backgrounds/Racketfire.png
cp pictures/Racketsplash.png static/backgrounds/Racketsplash.png
```

Weitere Bild-Themes lassen sich im `THEMES`-Dictionary in `app.py` ergaenzen, indem `background_image` auf den Dateinamen in `static/backgrounds/` gesetzt wird.

## Erklaervideo auf der Landing-Page

Die Landing-Page (`index.html`, Root des Repos) bindet das Erklaervideo `pictures/Matchtreff_Silber.mp4` direkt per HTML5-`<video>`-Tag ein. Der Pfad ist relativ zum Root, daher muss das Video im Ordner `pictures/` im Repo bleiben, damit die Landing-Page es korrekt anzeigt.

## Eintragsschutz gegen Doppel-Anmeldungen

- **Datenbank-Regel (hart):** Pro Slot ist ein normalisierter Name (getrimmt, klein geschrieben) nur einmal moeglich (`UNIQUE(slot_id, name_normalized)`), egal ueber welchen Kanal die Anmeldung erfolgt.
- **Cookie-Sperre (Web):** Nach erfolgreicher Anmeldung wird pro Slot ein Cookie im Browser gesetzt (`mtp_signed_<slot>`), das eine zweite Anmeldung ueber dasselbe Geraet fuer diesen Slot verhindert.
- **Telegram-ID-Sperre (Bot):** Im Bot verhindert die eindeutige Telegram-User-ID eine zweite Anmeldung fuer denselben Slot durch denselben Account.

## Warteliste

- Ist ein Slot voll, rutschen neue Anmeldungen automatisch auf eine **Warteliste** statt abgelehnt zu werden.
- Die Warteliste ist pro Slot auf **4 Eintraege** begrenzt (`WAITLIST_LIMIT = 4`), danach ist auch die Warteliste geschlossen.
- Loescht der Admin eine bestaetigte Anmeldung, rueckt automatisch die naechste Person von der Warteliste nach.
- Erhoeht der Admin die maximale Teilnehmerzahl eines Slots, rutschen ebenfalls automatisch so viele Wartelisten-Eintraege nach, wie neue Plaetze frei werden.

## Web-App: Features im Detail

- Anmeldung nur mit Namen - keine E-Mail-Adresse, kein Passwort, kein Account noetig
- Pro Slot eine vom Admin festgelegte maximale Teilnehmerzahl
- Live-Anzeige, wie viele Plaetze pro Slot noch frei sind
- Admin-Bereich (passwortgeschuetzt):
  - Maximale Teilnehmerzahl pro Slot aendern
  - Einzelne Anmeldungen loeschen
  - Alle Anmeldungen fuer die kommende Woche zuruecksetzen

## Telegram-Bot: Flow (Kurzfassung)

1. Bot in Telegram starten: `/start`
2. Aktuelle Slot-Belegung ansehen: `/slots`
3. Fuer einen Slot eintragen: `/eintragen <Name> <a|b|beide>`
   - Beispiel: `/eintragen MaxMustermann a`
   - Beispiel fuer beide Slots: `/eintragen MaxMustermann beide`
4. Eigenen Status abfragen: `/status <Name>`

### Admin-Befehle im Bot

Admins werden ueber die Telegram-User-ID in `ADMIN_TELEGRAM_IDS` festgelegt (kommagetrennt).

- `/admin_liste` - alle Anmeldungen fuer beide Slots anzeigen
- `/admin_max <a|b> <zahl>` - maximale Plaetze fuer einen Slot setzen
- `/admin_loeschen <id>` - einzelne Anmeldung per ID loeschen
- `/admin_reset` - alle Anmeldungen zuruecksetzen

Genau wie in der Web-App gilt: **nur Admins duerfen Anmeldungen aendern oder loeschen.**

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
export ADMIN_PASSWORD="change-me"    # Passwort fuer den Admin-Bereich
export PORT="1905"                   # Port fuer die Web-App
python app.py
```

Danach im Browser: `http://localhost:1905`

### Telegram-Bot starten

```bash
export TELEGRAM_BOT_TOKEN="dein-bot-token"
export ADMIN_TELEGRAM_IDS="123456789,987654321"
python telegram_bot.py
```

## Deployment via Portainer (Git-basiert)

Der Stack laesst sich in Portainer direkt aus diesem GitHub-Repository bereitstellen, ohne die Dateien manuell hochzuladen.

1. In Portainer unter **Stacks -> Add stack** gehen.
2. Als **Build method** die Option **Repository** waehlen (nicht "Web editor" oder "Upload").
3. Folgende Angaben eintragen:
   - **Repository URL:** `https://github.com/jbkunama1/hAI.MatchtreffPadel`
   - **Repository reference:** `refs/heads/main` (bzw. den Branch, in den gepusht wird)
   - **Compose path:** `docker-compose.yml`
4. Unter **Environment variables** die folgenden Werte setzen (echte, sichere Werte statt der Platzhalter):
   - `SECRET_KEY`
   - `ADMIN_PASSWORD`
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_TELEGRAM_IDS`
5. Optional: **GitOps updates** aktivieren (Polling oder Webhook), damit Portainer den Stack automatisch neu deployt, sobald neue Commits auf `main` gepusht werden.
6. Auf **Deploy the stack** klicken.

Portainer klont das Repository intern, baut die Images ueber das vorhandene `Dockerfile` und startet beide Services (`matchtreff_web`, `matchtreff_bot`) gemaess `docker-compose.yml`. Aenderungen am Code muessen nur noch gepusht werden - bei aktivierten GitOps-Updates zieht Portainer den Stand automatisch nach.

### Aktualisieren des Stacks

- Mit aktivierten GitOps-Updates: einfach `git push` auf `main` - Portainer aktualisiert den Stack automatisch nach dem konfigurierten Intervall bzw. per Webhook.
- Ohne GitOps-Updates: in Portainer beim Stack auf **Pull and redeploy** klicken, um den neuesten Commit zu holen und neu zu bauen.

## Docker / Portainer (manuelles Setup ohne Git-Integration)

### Image bauen

```bash
docker build -t haimatchtreffpadel:latest .
```

### Stack mit docker-compose (Web + Bot)

```bash
docker compose up -d
# oder: docker-compose up -d
```

`docker-compose.yml` definiert zwei Services:

```yaml
services:
  matchtreff_web:
    build: .
    container_name: matchtreff_padel_web
    command: gunicorn -b 0.0.0.0:1905 app:app
    ports:
      - "1905:1905"
    environment:
      - SECRET_KEY=change-me
      - ADMIN_PASSWORD=change-me
    volumes:
      - matchtreff_data:/app/instance
    restart: unless-stopped

  matchtreff_bot:
    build: .
    container_name: matchtreff_padel_bot
    command: python telegram_bot.py
    environment:
      - TELEGRAM_BOT_TOKEN=change-me
      - ADMIN_TELEGRAM_IDS=123456789
    volumes:
      - matchtreff_data:/app/instance
    restart: unless-stopped
    depends_on:
      - matchtreff_web

volumes:
  matchtreff_data:
```

- Web-App: erreichbar auf Port 1905
- Bot: laeuft im Hintergrund via Long Polling
- Beide Container teilen sich das Volume `matchtreff_data` (gleiche SQLite-Datenbank)

### Einsatz in Portainer

1. In Portainer unter **Stacks -> Add stack** gehen.
2. Inhalt der `docker-compose.yml` einfuegen.
3. `SECRET_KEY`, `ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN` und `ADMIN_TELEGRAM_IDS` auf echte Werte setzen.
4. Stack deployen.

## Sicherheit / Betrieb

- In Produktion immer einen starken `SECRET_KEY`, ein sicheres `ADMIN_PASSWORD` und einen geheimen `TELEGRAM_BOT_TOKEN` verwenden.
- Zugriff auf die Web-App ueber einen Reverse Proxy (nginx, Traefik, Cloudflare Tunnel) absichern.
- Volume `matchtreff_data` regelmaessig sichern (Backups).
- `ADMIN_TELEGRAM_IDS` nur mit den tatsaechlichen Telegram-User-IDs der Organisatoren befuellen.

## Admin-Funktionen (Web + Telegram)

| Funktion | Web-App | Telegram-Bot |
|---|---|---|
| Slot-Belegung ansehen | Startseite | `/slots`, `/admin_liste` |
| Anmelden | Formular mit Name + Slot-Auswahl | `/eintragen <Name> <a\|b\|beide>` |
| Max. Plaetze pro Slot setzen | Admin-Dashboard | `/admin_max <a\|b> <zahl>` |
| Anmeldung loeschen | Admin-Dashboard | `/admin_loeschen <id>` |
| Alle Anmeldungen zuruecksetzen | Admin-Dashboard | `/admin_reset` |
| Duplikatsschutz | DB-Unique + Cookie pro Slot | DB-Unique + Telegram-User-ID pro Slot |
| Warteliste (max. 4 pro Slot) | Ja, mit Auto-Nachruecken | Ja, mit Auto-Nachruecken |

Spieler selbst haben in beiden Kanaelen **keine** Moeglichkeit, ihre Anmeldung zu aendern oder zu loeschen - dies liegt bewusst ausschliesslich beim Admin.
