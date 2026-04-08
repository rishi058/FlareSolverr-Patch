import requests

# Format: socks5://username:password@host:port
proxy_url = "socks5://127.0.0.1:1080"

proxies = {
    "http": proxy_url,
    "https": proxy_url
}

try:
    # Testing against an IP echo service
    response = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
    print(f"Proxy Status: Success!")
    print(f"External IP via Proxy: {response.text}")
except Exception as e:
    print(f"Proxy Status: Failed")
    print(f"Error: {e}")