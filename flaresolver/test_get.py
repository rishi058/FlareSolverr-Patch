"""
Test the request.get command.
Run this from outside the container on your Windows machine.
"""
import requests
import json

FLARE_URL = "https://flaresolverr-latest-ympl.onrender.com/v1"

headers = {"Content-Type": "application/json"}

payload = {
    "cmd": "request.get",
    "url": "https://www.teraboxdl.site/",
}

print("Sending request.get to FlareSolverr...")

res = requests.post(FLARE_URL, headers=headers, json=payload, timeout=600)
data = res.text

with open("response_get.txt", "w") as f:
    f.write(data)

print("\nFull response saved to response_get.txt")