# Matchtreff Padel

Flask-Web-App zur Anmeldung fuer den woechentlichen Padel-Matchtreff (TPCG). Spieler
tragen sich pro Zeit-Slot ein, Admins verwalten Slots, Anmeldungen, Design und Texte
ueber ein eigenes Admin-Panel. Optional gibt es eine Telegram-Anbindung fuer
Gast-Benachrichtigungen.

## Funktionsumfang

### Anmeldung (oeffentliche Seite)
- Anmeldung per Name + Auswahl eines oder beider Zeit-Slots (Temprano 18-20 Uhr,
  Tarde 20-22 Uhr), Slot-Bezeichnungen sind im Admin-Panel frei editierbar.
- Checkbox "Ich bin TPCG-Mitglied" (standardmaessig angehakt, abwaehlbar). Jede
  Anmeldung - Mitglied oder Gast - wird sofort eingetragen (confirmed oder
  Warteliste), es gibt keinen Pending-Status. In der Anmeldeliste erscheint
  entsprechend ein "Mitglied"- oder "Gast"-Badge.
- Automatische Warteliste pro Slot (max. 4 Eintraege), sobald ein Slot voll ist.
- Orga-Team-Mitglieder (Daniel, Cosme, Sascha, Patrick) werden in der Liste mit
  einem Stern markiert.
- Anti-Doppel-Anmeldung: Ein Geraet kann sich pro Slot per Cookie nur einmal
  eintragen; zusaetzlich verhindert die Datenbank doppelte Namen pro Slot.
- Einleitungstext auf der Startseite mit Platzhalter {next_thursday}, der
  automatisch jede Woche durch das Datum des naechsten Donnerstags ersetzt wird.
- Eigene Info-Seite (/info) mit allen Rahmeninfos zum Matchtreff (Kosten,
  Ablauf, Golden Court, Gaeste-Regelung etc.), ueber das Hauptmenue erreichbar.

### Admin-Panel (/admin, Login unter /admin/login)
- Mehrere Admin-Accounts (Admin, Daniel, Cosme, Sascha, Patrick) mit eigenem
  Passwort je Account, verwaltbar unter "Admins verwalten" (Erstellen/Loeschen).
- Pro Slot: Bezeichnung und maximale Spieleranzahl aendern, bestaetigte
  Anmeldungen und Warteliste einsehen, einzelne Anmeldungen loeschen.
- Design/Hintergrund: Auswahl aus vordefinierten Farb-Themes (Standard/Blau,
  Sunset/Orange, Court/Gruen, Night/Dunkel) oder einem eigenen Hintergrundbild
  aus einer Bildergalerie (Kachel-Auswahl aus dem pictures-Verzeichnis).
- Schwebe-Effekt im Hintergrund umschaltbar: farbige Blasen oder grosse
  Padel-Ball-Icons.
- Einleitungstext der Startseite frei bearbeitbar (inkl. {next_thursday}-
  Platzhalter), Zuruecksetzen auf Standardtext moeglich.
- Gefahrenzone: Alle Anmeldungen auf einmal loeschen.

### Telegram-Anbindung (optional)
- Meldet sich ein Gast (kein Haken bei "Ich bin TPCG-Mitglied") an, erhalten
  alle in ADMIN_TELEGRAM_IDS hinterlegten Chat-IDs sofort eine Telegram-
  Nachricht mit Name, Slot und Status, inkl. Inline-Buttons "Bestaetigen" und
  "Entfernen". Die Anmeldung ist unabhaengig davon sofort im System gueltig.
  Fuer die Inline-Buttons muss telegram_bot.py parallel laufen (gleiche
  instance/-Datenbank per Volume mounten).

## Navigation / Menue

Die App nutzt eine feste Kopfzeile (Navbar) oben auf jeder Seite:
- Logo + Titel "Padel Matchtreff" links, verlinkt zur Startseite.
- Rechts: Startseite, Info-Seite ("MATCHTREFF Silber - Alle Infos"),
  Admin-Login bzw. Admin-Bereich/Logout (je nach Login-Status), sowie das
  "powered by TPC"-Logo.
- Auf Mobilgeraeten (< 768px) klappt die Navigation zu einem Hamburger-Menue
  zusammen; ein Klick zeigt alle Links untereinander in voller Breite.

## Projektstruktur

```
app.py                  Flask-App: Routen, DB-Init, Logik, Kontextvariablen
telegram_bot.py         Optionaler Telegram-Bot fuer Inline-Button-Aktionen
templates/
  base.html             Grundgeruest inkl. Navbar, Flash-Messages
  index.html            Anmeldeformular + Live-Anzeige der Slots
  info.html             Statische Info-Seite zum Matchtreff
  admin_login.html      Admin-Login-Formular
  admin_dashboard.html  Slot-/Anmeldungs-/Design-/Text-Verwaltung
  admin_users.html      Admin-Accounts verwalten
static/
  style.css             Gesamtes Styling (Karten, Buttons, Navbar, Mobile)
  pictures/             Bildergalerie fuer eigene Hintergruende
Dockerfile               Container-Build (gunicorn, Port 1905)
requirements.txt         Flask, gunicorn, python-telegram-bot
.env.example             Vorlage fuer noetige Umgebungsvariablen
```

## Setup

1. Alle Originalbilder aus dem pictures-Ordner nach static/pictures/ kopieren
   (Dateinamen 1:1 wie im GitHub-Repo, siehe GALLERY_IMAGES in app.py).
2. .env nach Vorlage .env.example ausfuellen:
   - Pflicht: SECRET_KEY, ADMIN_PASSWORD_ADMIN, ADMIN_PASSWORD_DANIEL
   - Optional: ADMIN_PASSWORD_COSME/SASCHA/PATRICK fuer weitere Admin-Accounts
   - Optional: TELEGRAM_BOT_TOKEN + ADMIN_TELEGRAM_IDS fuer Gast-Benachrichtigungen
3. Mit Docker: `docker build -t matchtreff-padel .` und Container starten
   (Port 1905), oder lokal: `pip install -r requirements.txt && python app.py`
4. Optional fuer die Telegram-Inline-Buttons: `python telegram_bot.py` parallel
   starten (gleiche instance/-Datenbank per Volume mounten).

Die SQLite-Datenbank wird beim ersten Start automatisch unter instance/ angelegt
und mit den Standard-Slots, Admin-Accounts und Einstellungen befuellt.
