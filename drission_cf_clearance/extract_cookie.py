import time
import json
import os
from DrissionPage import ChromiumPage, ChromiumOptions

def extract():
    print("Launching browser...")
    # Using persistent profile to make use of existing browser cache if possible
    base = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Temp"
    profile_dir = os.path.join(base, "ts_profile_drission")

    co = ChromiumOptions()
    co.set_user_data_path(profile_dir)
    
    page = ChromiumPage(co)
    
    print("Navigating to https://www.teraboxdl.site/ ...")
    try:
        page.get('https://www.teraboxdl.site/')
    except Exception as e:
        print(f"Note on navigation (can happen with CF challenges): {e}")
    
    print("Waiting 15 seconds for Cloudflare auto-bypass to complete...")
    time.sleep(6) 
    
    print("Extracting cookies and User-Agent...") 
    cookies = page.cookies(all_domains=True)
    user_agent = page.run_js("return navigator.userAgent")
    
    cf_clearance = None
    all_cookies_dict = {}
    
    for cookie in cookies:
        all_cookies_dict[cookie["name"]] = cookie["value"]
        if cookie["name"] == 'cf_clearance':
            cf_clearance = cookie["value"]
            
    if not cf_clearance:
        print("WARNING: 'cf_clearance' cookie not found! Cloudflare might still block you.")
    else:
        print(f"SUCCESS! Found cf_clearance: {cf_clearance[:15]}...")
        
    session_data = {
        "userAgent": user_agent,
        "cookies": all_cookies_dict
    }
    
    with open("session_data.json", "w") as f:
        json.dump(session_data, f, indent=4)
        
    print("Saved session data to session_data.json")
    page.quit()

if __name__ == '__main__':
    extract()
