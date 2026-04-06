"""
Test the request.get command.
Run this from outside the container on your Windows machine.
"""
import requests
import json

FLARE_URL = "http://localhost:8191/v1"

headers = {"Content-Type": "application/json"}

payload = {
    "cmd": "request.get",
    "url": "__",
}

print("Sending request.get to FlareSolverr...")

res = requests.post(FLARE_URL, headers=headers, json=payload, timeout=600)
data = res.json()

with open("response_get.json", "w") as f:
    json.dump(data, f, indent=2)

print("\nFull response saved to response_get.json")