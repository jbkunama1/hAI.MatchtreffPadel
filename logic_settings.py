from zoneinfo import ZoneInfo

# Statische Definitionen
SLOT_DEFINITIONS = [
    {"key": "slot_a", "label": "Temprano: 18:00 - 20:00 Uhr"},
    {"key": "slot_b", "label": "Tarde: 20:00 - 22:00 Uhr"},
]
SLOT_LABEL = {slot["key"]: slot["label"] for slot in SLOT_DEFINITIONS}

WAITLIST_LIMIT = 4
DEFAULT_SLOT_SELECTION = "both"
DEFAULT_WAITLIST_MODE = "with_waitlist"
WAITLIST_MODES = {
    "with_waitlist",
    "open_for_all",
    "no_waitlist",
    "guests_only",
}

DEFAULT_MAX_PLAYERS = 14
DEFAULT_THEME = "night"
DEFAULT_BG_STYLE = "bubbles"
DEFAULT_CUSTOM_IMAGE = "Racketfire.png"
SIGNUP_COOKIE_PREFIX = "mtp_signed_"
DEFAULT_SHOW_BANNER = "1"

# Automatik / Scheduler Defaults
DEFAULT_RESET_ENABLED = "1"
DEFAULT_RESET_WEEKDAY = "4"  # 0=Montag ... 4=Freitag
DEFAULT_RESET_HOUR = "6"
DEFAULT_RESET_MINUTE = "0"
DEFAULT_NOTIFY_INTERVAL_MINUTES = "60"
DEFAULT_REMINDER_ENABLED = "1"
DEFAULT_REMINDER_WEEKDAY = "3"  # 0=Montag ... 3=Donnerstag (Spieltag)
DEFAULT_REMINDER_HOUR = "12"
DEFAULT_REMINDER_MINUTE = "0"
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Anmeldesperre Defaults
DEFAULT_SIGNUP_LOCK_ENABLED = "1"
DEFAULT_SIGNUP_LOCK_MANUAL_OPEN = "0"
DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT = ""
SIGNUP_DEFAULT_OPEN_WEEKDAY = 1  # 0=Mo ... 1=Di
SIGNUP_DEFAULT_OPEN_HOUR = 13
SIGNUP_DEFAULT_OPEN_MINUTE = 0
APP_TZ = ZoneInfo("Europe/Berlin")

DEFAULT_INTRO_TEXT = (
    "Anmeldung fuer Donnerstag, {next_thursday}. Trag einfach deinen Namen ein "
    "und waehle einen oder beide Slots. Pro Geraet kann man sich pro Slot nur "
    "einmal eintragen."
)

INFO_PAGE_TEXT = """Hallo Padel-Spieler,

hier findet Ihr die Abfrage, wer so alles beim MATCHTREFF SILBER dabei ist.

Ich habe uns aktuell 3 Plaetze reserviert von 18 - 22 Uhr.

Wuerde mich freuen, wenn wir uns am Donnerstag sehen!
Das ganze findet natuerlich nur statt, wenn es das Wetter auch zulaesst.
Ihr koennt jederzeit dazukommen, entweder direkt ab 18 Uhr, oder auch spaeter ab 20 Uhr.
Bitte beachtet diese Startzeiten, damit wir auch immer genuegend Spieler sind und nicht warten muessen.

Ich bekomme bitte von jedem Teilnehmer 2 Euro (TCG-Mitglieder), das nutzen wir,
um zum Beispiel Baelle fuer den Matchtreff zu organisieren.

Gaeste (Nicht-TCG-Mitglieder) sind willkommen, zahlen aber pauschal 15 Euro.
Gaeste bitte unbedingt vorher bei mir anmelden. TCG-Mitglieder haben Vorrang.

Wann immer es geht, spielen wir Golden Court, je nach Teilnehmerzahl.

In unregelmaessigen Abstaenden wird donnerstags auch ein GPS100 DPV angeboten.
Ausserdem wird es ab dieser Saison immer wieder ein AMERICANO geben.

Das Angebot richtet sich an Spieler auf SILBER-Level.
Fuer Anfaenger und Interessierte gibt es montags ein Angebot.

Tragt euch ein, wer dabei ist!

Danke und Gruss
Daniel

Fragen? Immer gerne, entweder per WhatsApp oder per Mail:
daniel@will-padel-spielen.de
"""

GALLERY_IMAGES = [
    "1716335274392.png", "1716335619157.png", "Designer (1).jpeg", "Designer (10).jpeg",
    "Designer (11).jpeg", "Designer (12).jpeg", "Designer (13).jpeg", "Designer (14).jpeg",
    "Designer (2).jpeg", "Designer (3).jpeg", "Designer (4).jpeg", "Designer (5).jpeg",
    "Designer (6).jpeg", "Designer (7).jpeg", "Designer (8).jpeg", "Designer (9).jpeg",
    "Designer.jpeg", "Designer1.jpeg", "Designer_Paypal_1.jpeg", "Designer_Paypal_2.jpeg",
    "Download.png", "FollowLogo.jpeg", "Racketfire.png", "Racketsplash.png",
    "image_fx_a__flyer_for_a_padel_tennis_event_called__ma.jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (1).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (2).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (3).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without.jpg",
    "image_fx_a_flyer_for_a_padel_tennis_event_without_any.jpg",
]

THEMES = {
    "default": {
        "label": "Standard (Blau)",
        "gradient": "radial-gradient(circle at top left, #e0ecff 0, #f5f5fb 40%, #fdfdfd 100%)",
        "background_image": None, "accent": "#2563eb", "accent2": "#0ea5e9",
    },
    "sunset": {
        "label": "Sunset (Orange)",
        "gradient": "radial-gradient(circle at top left, #ffe4d6 0, #fff5f0 40%, #fffaf7 100%)",
        "background_image": None, "accent": "#ea580c", "accent2": "#f59e0b",
    },
    "court": {
        "label": "Court (Gruen)",
        "gradient": "radial-gradient(circle at top left, #dcfce7 0, #f0fdf4 40%, #fbfffc 100%)",
        "background_image": None, "accent": "#16a34a", "accent2": "#22c55e",
    },
    "night": {
        "label": "Night (Dunkel)",
        "gradient": "radial-gradient(circle at top left, #1e293b 0, #0f172a 60%, #020617 100%)",
        "background_image": None, "accent": "#38bdf8", "accent2": "#818cf8",
    },
    "custom_image": {
        "label": "Eigenes Bild (Galerie)",
        "gradient": "linear-gradient(rgba(15,23,42,0.55), rgba(15,23,42,0.55))",
        "background_image": "__CUSTOM__", "accent": "#f97316", "accent2": "#facc15",
    },
}

BG_STYLES = {"bubbles": "Farbige Blasen", "logo": "Padel-Ball-Icons"}
ORGA_TEAM = ["Daniel", "Cosme", "Sascha", "Patrick"]


def normalize_name(name: str) -> str:
    return " ".join(str(name).strip().split()).lower()

ORGA_TEAM_NORMALIZED = {normalize_name(name) for name in ORGA_TEAM}


def get_setting_defaults():
    return {
        "theme": DEFAULT_THEME,
        "bg_style": DEFAULT_BG_STYLE,
        "custom_bg_image": DEFAULT_CUSTOM_IMAGE,
        "waitlist_limit": str(WAITLIST_LIMIT),
        "slot_selection": DEFAULT_SLOT_SELECTION,
        "waitlist_mode": DEFAULT_WAITLIST_MODE,
        "reset_enabled": DEFAULT_RESET_ENABLED,
        "reset_weekday": DEFAULT_RESET_WEEKDAY,
        "reset_hour": DEFAULT_RESET_HOUR,
        "reset_minute": DEFAULT_RESET_MINUTE,
        "notify_interval_minutes": DEFAULT_NOTIFY_INTERVAL_MINUTES,
        "reminder_enabled": DEFAULT_REMINDER_ENABLED,
        "reminder_weekday": DEFAULT_REMINDER_WEEKDAY,
        "reminder_hour": DEFAULT_REMINDER_HOUR,
        "reminder_minute": DEFAULT_REMINDER_MINUTE,
        "signup_lock_enabled": DEFAULT_SIGNUP_LOCK_ENABLED,
        "signup_lock_manual_open": DEFAULT_SIGNUP_LOCK_MANUAL_OPEN,
        "signup_lock_auto_open_at": DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT,
        "show_banner": DEFAULT_SHOW_BANNER,
    }
