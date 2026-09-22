with open("templates/admin_dashboard.html", "r", encoding="utf-8") as f:
    content = f.read()

new_content = content.replace(
    'action="{{ url_for(\'admin_settings_save\') }}"',
    'action="{{ url_for(\'admin_update_americana_ad\') }}"'
)

with open("templates/admin_dashboard.html", "w", encoding="utf-8") as f:
    f.write(new_content)
print("Done")
