from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("Europe/Berlin")

def next_thursday_test(now):
    today = now.date()
    if today.weekday() == 3:
        return today
    elif today.weekday() == 4 and now.hour < 6:
        return today - timedelta(days=1)
    days_ahead = (3 - today.weekday()) % 7
    return today + timedelta(days=days_ahead)

cases = [
    (datetime(2026, 8, 6, 12, 50, tzinfo=APP_TZ), "2026-08-06"),  # Thu midday -> this week
    (datetime(2026, 8, 7, 5, 59, tzinfo=APP_TZ), "2026-08-06"),  # Fri before 6am -> still this week
    (datetime(2026, 8, 7, 6, 1, tzinfo=APP_TZ), "2026-08-13"),   # Fri after 6am -> next week
    (datetime(2026, 8, 10, 10, 0, tzinfo=APP_TZ), "2026-08-13"), # Monday -> next Thursday
]

for now, expected in cases:
    result = next_thursday_test(now)
    assert str(result) == expected, f"{now} -> {result}, expected {expected}"

print("All 4 cases passed")
