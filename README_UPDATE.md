# hAI.MatchtreffPadel – Update-Paket (Reset, Digest, Backup, Edit, Video)

Dieses Paket enthält NUR die besprochenen Erweiterungen. Das Design/Layout
bleibt unverändert – alle bestehenden Funktionen (Anmeldung, Warteliste,
Admin-Login, Themes, Telegram-Gast-Benachrichtigung) funktionieren exakt
wie vorher.

## Was ist neu?

1. **Automatischer wöchentlicher Reset**
   - Standard: jeden Freitag 06:00 Uhr, löscht ALLE Anmeldungen komplett
     (neue Woche, neuer Anfang).
   - Konfigurierbar direkt im Admin-Dashboard unter "Automatik" (kein
     Umgebungsvariablen-Frickeln mehr nötig).

2. **60-Minuten-Digest**
   - Sammelt neue Anmeldungen und schickt alle 60 Minuten (konfigurierbar)
     EINE Zusammenfassung an die Telegram-Admins (ADMIN_TELEGRAM_IDS).
   - Geht NICHT an E-Mail, nur an Telegram-Admins.
   - Gäste bekommen weiterhin sofort ihre eigene Nachricht wie bisher.

3. **Backup-Download**
   - Neuer Button im Admin-Dashboard: "Backup herunterladen".
   - Erstellt über die SQLite-Online-Backup-API eine konsistente Kopie der
     Datenbank, auch bei laufendem Schreibzugriff.

4. **Einträge bearbeiten**
   - Neuer "Bearbeiten"-Link bei jedem Signup (Bestätigt + Warteliste).
   - Name, Mitglied/Gast-Status, Slot und Status (bestätigt/Warteliste)
     können angepasst werden, inkl. Dubletten- und Kapazitätsprüfung.

5. **Erklärvideo auf der Info-Seite**
   - Auf der bereits vorhandenen Seite `/info` ("MATCHTREFF Silber - Alle
     Infos dazu gibt es hier") wird das Video `Matchtreff_Silber.mp4`
     zusätzlich direkt abspielbar eingebunden (HTML5 `<video>`-Player).

## Was du konkret tun musst

### 1. Dateien ins Repo übernehmen

- `app.py` → ersetzt die bestehende Datei komplett (enthält alle bisherigen
  Routen unverändert + die neuen Routen für Automatik, Backup, Edit).
- `requirements.txt` → ersetzt die bestehende Datei (nur `APScheduler`
  wurde ergänzt).
- `docker-compose.yml` → ersetzt die bestehende Datei (neuer dritter
  Service `matchtreff_scheduler`, alles andere unverändert).
- `scheduler.py` → NEUE Datei im Projekt-Root.
- `templates/info.html` → ersetzt die bestehende Datei (Video ergänzt).
- `templates/admin_edit_signup.html` → NEUE Datei.

### 2. Video-Datei bereitstellen

Kopiere `Matchtreff_Silber.mp4` (liegt aktuell im Repo-Root) nach:

```
static/Matchtreff_Silber.mp4
```

Damit kann Flask sie wie alle anderen statischen Assets (Bilder, Logos)
ausliefern.

### 3. admin_dashboard.html von Hand ergänzen

Aus Sicherheitsgründen wurde `admin_dashboard.html` NICHT automatisch
überschrieben, da diese Datei sehr individuell ist (Themes, Galerie,
Slot-Verwaltung). Die exakten Ergänzungen (3 Stellen: Bearbeiten-Link,
Automatik-Bereich, Backup-Button) stehen fertig formuliert in:

```
ADMIN_DASHBOARD_AENDERUNGEN.txt
```

Einfach die dort beschriebenen HTML-Blöcke an den passenden Stellen in
deine bestehende `templates/admin_dashboard.html` einfügen. Es wird kein
neues CSS benötigt, nur bereits im Projekt vorhandene Bootstrap-Klassen.

### 4. Deployment

1. Alle Dateien committen und pushen.
2. In Portainer: Stack "Pull and redeploy".
3. Danach sollten drei Container laufen:
   - `matchtreff_padel_web`
   - `matchtreff_padel_bot`
   - `matchtreff_padel_scheduler` (NEU)

Die Automatik-Einstellungen (Wochentag/Uhrzeit/Intervall) kannst du danach
direkt im Admin-Dashboard einstellen. Der Scheduler-Container liest sie beim
Start; Änderungen an Wochentag/Uhrzeit/Intervall werden erst nach einem
Neustart des `matchtreff_padel_scheduler`-Containers aktiv (einfach in
Portainer neu deployen). Das Ein-/Ausschalten des Resets (Checkbox) wirkt
sofort beim nächsten geplanten Lauf, ohne Neustart.

## Was bewusst NICHT verändert wurde

- Kein neues Design, keine neuen Farben/Fonts.
- Keine Änderung an bestehenden Routen-Signaturen oder URLs.
- Keine Änderung am Cookie-/Warteliste-/Mitglieder-Verhalten.
- Kein E-Mail-Versand – Digests bleiben ausschließlich auf Telegram-Admins
  beschränkt, wie gewünscht.
