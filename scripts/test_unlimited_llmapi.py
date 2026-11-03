import urllib.request
import urllib.error
import json

url = "http://192.168.55.2:8080/v1/chat/completions"
api_key = "ulk_GDET8pmQAcAO2WvhM7kKTSF-Bs6OJoJYO5gehBvgvf8"

payload = json.dumps({
    "model": "gemini-3.8-flash",
    "messages": [{"role": "user", "content": "respond with JSON: {\"points\": [\"test\"]}"}]
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Hermes-Agent": "wisdom-oldman"
    }
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("SUCCESS:", resp.status)
        print(resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode())
except Exception as e:
    print("Error:", e)
