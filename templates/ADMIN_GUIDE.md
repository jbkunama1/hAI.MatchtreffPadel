# Admin‑Guide für hAI.MatchtreffPadel

## Rollen & Rechte

### Nutzer (Spieler / End‑User)
- **Anmeldung ohne Login** – nur Name eingeben, optional Mitglied‑/Gast‑Kennzeichen.
- **Slot‑Auswahl** (A 18‑20 Uhr, B 20‑22 Uhr) – live freie Plätze sehen.
- **Warteliste** wird automatisch geführt, rückt bei freien Plätzen nach.
- **Kommentar‑Feld** unter der öffentlichen Liste.
- **Download‑Bereich** für Bilder, APKs usw.
- **Schutz**: keine Doppel‑Anmeldungen (Name‑Normalisierung, Cookie, Telegram‑User‑ID).
- **Anmelde‑Sperre**: Standard ist geschlossen – Admin kann öffnen/manuell freigeben oder automatisieren.

### Admins
- **Login** über `/admin/login` (Passwort‑gehasht).
- **Slot‑Limits** und Bezeichnung ändern, Slots aktivieren/deaktivieren.
- **Einträge** bearbeiten, löschen, bestätigen (grüne Markierung).
- **Wöchentlicher Reset** – alle Anmeldungen zurücksetzen, Sperre wieder schließen.
- **Wartelisten‑Einstellungen** (Modus, Gäste‑Zulassung, Max‑Größe).
- **Anmelde‑Sperre** manuell öffnen/schließen oder automatische Freigabe planen.
- **Automatik (Scheduler)**: Reset, Digest, Reminder konfigurieren.
- **Design & Hintergrund**: Theme wählen, Bild/Schwebe‑Effekt setzen, Intro‑Text bearbeiten.
- **Telegram‑Bot**: Admin‑IDs festlegen, Broadcast, Bot‑Einstellungen.
- **Admin‑Verwaltung**: neue Admins anlegen, entfernen (letzter Admin kann nicht gelöscht werden, Selbslöschung nicht möglich).
- **Backup & Export**: Datenbank‑Backup herunterladen, CSV‑Export.
- **FAQ‑Management**: Fragen/Antworten hinzufügen, sortieren.
- **Hinweis‑Text** auf Startseite – zeigt Öffnungszeiten/automatische Freigabe.

## Schnell‑Einrichtung für neue Admins
1. **Login** unter `/admin/login` mit bereitgestelltem Benutzernamen/Passwort.
2. **Anmelde‑Sperre öffnen** (Tab **🔒 Anmeldung**) – so können Nutzer sofort eintragen.
3. **Slot‑Limits prüfen** (Tab **⚙️ Admin‑Dashboard**) und ggf. anpassen.
4. **Wartelisten‑Modus** einstellen, falls Gäste‑Warteliste gewünscht ist.
5. **Design** auswählen (Tab **🎨 Design & Hintergrund**) – ggf. Hintergrund‑Bild hochladen.
6. **Automatik** aktivieren (Tab **⚙️ Automatik**) – Reset‑Zeit, Digest‑Intervall, Reminder‑Zeitpunkte setzen.
7. **Telegram‑Bot** konfigurieren (Tab **📲 Telegram‑Kanal**) – Bot‑Token, Admin‑IDs eintragen.
8. **Backup** regelmäßig herunterladen (Tab **💾 Datenbank‑Backup**) und bei Bedarf wiederherstellen.
9. **FAQ** ergänzen für häufige Nutzer‑Fragen (Tab **❓ FAQ‑Einträge**).
10. **Hinweis‑Text** auf Startseite anpassen (Tab **📝 Einleitungstext**) – wann die Anmeldung öffnet.

## Hinweis für Admins
- **Doppelte Anmeldung** wird von Web‑ und Bot‑Logik verhindert – prüft Name, Cookie und Telegram‑User‑ID.
- **Warteliste** ist pro Slot auf **4** Einträge begrenzt.
- **Automatischer Reset** (standard Freitag 06:00 Uhr) schließt die Anmeldung wieder.
- **Admins können sich immer eintragen**, unabhängig vom Sperr‑Status.
- **Letzter Admin** kann nicht gelöscht werden; ein Admin kann sich nicht selbst entfernen.
- **Passwort** sollte in Produktion stark und geheim sein (`SECRET_KEY`, `ADMIN_PASSWORD_*`).

---
*Diese Anleitung wird im Admin‑Dashboard verlinkt.*
