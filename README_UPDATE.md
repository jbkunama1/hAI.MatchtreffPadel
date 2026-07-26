# Matchtreff Padel - Update

Aenderungen in diesem Stand gegenueber GitHub:

1. Gast-Anmeldung ohne Pending: Jede Anmeldung (Mitglied oder Gast) wird sofort
   eingetragen (confirmed/waitlist wie gehabt), es gibt keinen Pending-Status mehr.
   Ueber die Checkbox "Ich bin TPCG-Mitglied" (standardmaessig angehakt, abwaehlbar)
   wird zwischen Mitglied und Gast unterschieden; entsprechend erscheint ein
   "Mitglied"- oder "Gast"-Badge in der Anmeldeliste.

2. Telegram-Benachrichtigung bei Gast-Anmeldung: Meldet sich jemand OHNE Haken bei
   "Ich bin TPCG-Mitglied" an, bekommen alle in ADMIN_TELEGRAM_IDS hinterlegten
   Chat-IDs sofort eine Telegram-Nachricht mit Name, Slot und Status, plus zwei
   Inline-Buttons ("Bestaetigen" / "Entfernen"). Admins koennen die Anmeldung
   jederzeit im Admin-Dashboard oder direkt per Telegram-Button entfernen; die
   Anmeldung selbst war aber sofort gueltig und im System.
   Fuer die Inline-Buttons zusaetzlich telegram_bot.py starten (gleiche
   instance/-Datenbank per Volume mounten).

3. Admin-Panel: "Design mit Bild" repariert und Bildergalerie ergaenzt: Alle
   Bilder aus dem pictures-Verzeichnis werden im Admin-Dashboard als Auswahl-
   Kacheln angezeigt. Auswahl + "Bild als Hintergrund uebernehmen" setzt das
   Bild als Hintergrund und aktiviert automatisch das Design "Eigenes Bild
   (Galerie)".

4. Hintergrund-Icons 4x groesser: Die schwebenden Padel-Ball-Icons sind jetzt
   ca. 4x so gross wie zuvor (36-80px statt 9-20px).

5. Automatisches Donnerstagsdatum: Der Text "Anmeldung fuer Donnerstag,
   TT.MM.JJJJ." verwendet den Platzhalter {next_thursday}, der bei jedem
   Seitenaufruf live durch das Datum des naechsten Donnerstags ersetzt wird.
   Sobald der Donnerstag vorbei ist, zeigt die Seite automatisch den naechsten
   Donnerstag - ganz ohne manuelles Eingreifen. Der Text bleibt im Admin-Panel
   frei editierbar (mit dem Platzhalter im Text).

## Setup

1. Alle Originalbilder aus dem pictures-Ordner nach static/pictures/ kopieren
   (Dateinamen 1:1 wie im GitHub-Repo, siehe GALLERY_IMAGES in app.py).
2. .env nach Vorlage .env.example ausfuellen (SECRET_KEY, Admin-Passwoerter,
   optional TELEGRAM_BOT_TOKEN + ADMIN_TELEGRAM_IDS).
3. docker build -t matchtreff-padel . und starten, oder lokal:
   pip install -r requirements.txt && python app.py
4. Optional fuer Telegram-Buttons: python telegram_bot.py parallel starten.
