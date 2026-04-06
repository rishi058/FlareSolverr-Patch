"""
Test the new request.post2 command.
Run this from outside the container on your Windows machine.
"""
import requests
import json

FLARE_URL = "http://localhost:8191/v1"

payload = {
    "cmd": "request.post2",
    "base_url": "__",
    "post_endpoint": "__",
    "post_json_body": "__"
}

print("Sending request.post2 to FlareSolverr...")
res = requests.post(FLARE_URL, json=payload, timeout=600)
data = res.json()

with open("response_post2.json", "w") as f:
    json.dump(data, f, indent=2)

print("\nFull response saved to response_post2.json")

