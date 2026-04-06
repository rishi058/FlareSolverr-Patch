import asyncio
import re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Launch Chromium (or Google Chrome) in headful mode
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        log_file = open("network_log.txt", "w", encoding="utf-8")
        found_sitekeys = set()

        def handle_request(request):
            url = request.url
            log_file.write(f"REQUEST [{request.method}] {url}\n")
            log_file.flush()
            
            # Extract Turnstile sitekey
            if "challenges.cloudflare.com" in url and "0x4A" in url:
                match = re.search(r'(0x4A[a-zA-Z0-9_-]+)', url)
                if match:
                    sitekey = match.group(1)
                    if sitekey not in found_sitekeys:
                        found_sitekeys.add(sitekey)
                        print(f"[*] Found Turnstile Sitekey: {sitekey}")
                        with open("output.txt", "a", encoding="utf-8") as out_file:
                            out_file.write(f"{sitekey}\n")

        def handle_response(response):
            log_file.write(f"RESPONSE [{response.status}] {response.url}\n")
            log_file.flush()

        page.on("request", handle_request)
        page.on("response", handle_response)

        try:
            print("Navigating to https://www.teraboxdl.site/ ...")
            # We don't wait for networkidle because cloudflare might continuously poll
            await page.goto("https://www.teraboxdl.site/", timeout=60000)
            print("Page opened. Waiting 20 seconds to capture challenge and redirects...")
            await asyncio.sleep(20)
        except Exception as e:
            print(f"Exception: {e}")
        finally:
            print("Closing browser and saving logs...")
            log_file.close()
            await browser.close()
            print("Network log has been saved to network_log.txt")

if __name__ == "__main__":
    asyncio.run(main())
