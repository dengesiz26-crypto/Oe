python - <<'PY'
import os
import requests

key = (
    os.getenv("GOALDIR_API_KEY")
    or os.getenv("BSD_API_KEY")
    or ""
).strip()

url = "https://sports.bzzoiro.com/api/v2/leagues/"

r = requests.get(
    url,
    headers={
        "Authorization": f"Token {key}",
        "Accept": "application/json",
    },
    params={"limit": 200},
    timeout=30,
)

print("STATUS:", r.status_code)
print(r.text[:5000])
PY
