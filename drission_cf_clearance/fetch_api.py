import json
import requests

"""
that cf clearence cookie is not like simple cookie... its binding with your ip address, tls fingerprinting, 
webgl canvas which are only available via real browser..
"""

def fetch_terabox_data(target_url):
    try:
        with open("session_data.json", "r") as f:
            session_data = json.load(f)
    except FileNotFoundError:
        print("ERROR: session_data.json not found!")
        print("Please run extract_cookie.py first to generate it.")
        return

    # To bypass Cloudflare WAF, you must pass the exact same User-Agent 
    # that generated the cf_clearance cookie.
    headers = {
        "User-Agent": session_data["userAgent"],
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://teraboxdl.site",
        "Referer": "https://teraboxdl.site/"
    }

    payload = {
        "url": target_url
    }

    api_url = "https://teraboxdl.site/api/proxy"
    
    print(f"Sending POST request to {api_url}")
    print(f"Target URL: {target_url}\n")
    
    try:
        # Pass the extracted cookies dict directly to requests
        response = requests.post(
            api_url, 
            headers=headers, 
            cookies=session_data["cookies"], 
            json=payload,
            timeout=15
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 403:
            print("FAILED: Cloudflare blocked the request (403 Forbidden).")
            print("The cf_clearance cookie might be expired or the headers are missing.")
        else:
            print("Response:")
            try:
                print(response.status_code)
                with open("response.json", "w") as f:
                    json.dump(response.json(), f, indent=4)

            except json.JSONDecodeError:
                # Fallback to plain text
                print(response.text)
                
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")

if __name__ == '__main__':
    target = "https://1024terabox.com/s/17OqJOK1LAqc0GJ7dK5tkbg"
    fetch_terabox_data(target)
