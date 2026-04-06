"""
post2/handler.py — Implements the request.post2 command for FlareSolverr.

request.post2 flow:
  1. Check db.json for a cached session for base_url.
  2. If MISS → call _solve_and_cache() to run request.get on base_url,
     then cache userAgent + cookies.
  3. Make a JSON POST to base_url + post_end_point using the cached session
     from INSIDE the container (so IP matches the one that solved the challenge).
  4. If the POST returns 403 → evict cache, re-solve ONCE, retry POST.
     If still 403 → return the 403 response (don't loop).
  5. Return a rich response dict to the caller.
"""
import json
import logging
import time
from urllib.parse import urljoin

import requests as stdlib_requests

from dtos import STATUS_OK, STATUS_ERROR, V1RequestBase, V1ResponseBase
from post2 import db


# ──────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────

def cmd_request_post2(req: V1RequestBase) -> V1ResponseBase:
    """Handle the request.post2 command."""
    start_ts = int(time.time() * 1000)

    # ── Validate required fields ──────────────────────────────────────────
    if not req.base_url:
        return _error_response("Request parameter 'base_url' is mandatory.", start_ts)
    if not req.post_endpoint:
        return _error_response("Request parameter 'post_endpoint' is mandatory.", start_ts)
    if req.post_json_body is None:
        return _error_response("Request parameter 'post_json_body' is mandatory.", start_ts)

    base_url = req.base_url.rstrip("/") + "/"
    post_url = urljoin(base_url, req.post_endpoint)

    # Parse the JSON body (accepts string or dict)
    try:
        if isinstance(req.post_json_body, str):
            json_body = json.loads(req.post_json_body)
        else:
            json_body = req.post_json_body
    except (json.JSONDecodeError, TypeError) as e:
        return _error_response(f"'post_json_body' is not valid JSON: {e}", start_ts)

    max_timeout = int(req.maxTimeout or 60000)
    logging.info(f"[post2] base_url={base_url}  post_url={post_url}")

    # ── Step 1: Ensure we have a cached session ───────────────────────────
    session = db.get(base_url)
    if session is None:
        logging.info(f"[post2] Cache MISS for {base_url} — solving CF challenge...")
        session = _solve_and_cache(base_url, max_timeout)
        if session is None:
            return _error_response(
                f"Failed to solve Cloudflare challenge for {base_url}.", start_ts
            )

    # ── Step 2: Make the JSON POST ────────────────────────────────────────
    resp_data, status_code, error = _do_post(post_url, json_body, session)

    # ── Step 3: Handle 403 (stale cookie) — ONE retry ────────────────────
    if status_code == 403:
        logging.info(f"[post2] Got 403 — evicting cache and retrying once for {base_url}")
        db.remove(base_url)
        session = _solve_and_cache(base_url, max_timeout)
        if session is None:
            return _error_response(
                "Got 403 and failed to refresh Cloudflare session.", start_ts
            )
        resp_data, status_code, error = _do_post(post_url, json_body, session)

    # ── Build response ────────────────────────────────────────────────────
    elapsed_sec = round((time.time() * 1000 - start_ts) / 1000)
    res = V1ResponseBase({})
    res.time_taken = f"{elapsed_sec} sec"

    if error and status_code != 200:
        res.status = STATUS_ERROR
        res.message = error
        res.target_url_response = {
            "status_code": status_code,
            "body": None,
            "error": error,
        }
    else:
        res.status = STATUS_OK
        res.message = "OK"
        res.target_url_response = {
            "status_code": status_code,
            "body": resp_data,
            "error": None,
        }

    return res


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _solve_and_cache(base_url: str, max_timeout: int) -> dict | None:
    """
    Directly invoke FlareSolverr's internal request.get handler to solve the
    CF challenge (no HTTP round-trip — works on Render / any platform).
    Persists full session data (cookies, headers incl. User-Agent)
    to db.json and returns a session dict.
    Returns None on failure.
    """
    # Lazy import to avoid circular dependency
    # (flaresolverr_service imports post2.handler at module level)
    from flaresolverr_service import _cmd_request_get

    try:
        # Build a minimal V1RequestBase for request.get
        internal_req = V1RequestBase({
            "cmd": "request.get",
            "url": base_url,
            "maxTimeout": max_timeout,
            "returnOnlyCookies": False,  # we want headers too
        })
        res = _cmd_request_get(internal_req)
    except Exception as e:
        logging.error(f"[post2] Error solving CF challenge for {base_url}: {e}")
        return None

    if res.status != STATUS_OK:
        logging.error(f"[post2] CF challenge failed for {base_url}: {res.message}")
        return None

    solution = res.solution
    if solution is None:
        logging.error(f"[post2] No solution returned for {base_url}")
        return None

    user_agent = solution.userAgent or ""
    cookies = solution.cookies or []        # list of Selenium cookie dicts
    headers = solution.headers or {}        # response headers (if available)
    # Merge User-Agent into headers so everything lives in one place
    headers["User-Agent"] = user_agent
    # NOTE: cf_clearance is already inside `cookies` as a dict with
    #       {"name": "cf_clearance", "value": "...", ...}
    #       No need to extract it separately — it's saved with all cookies.

    db.put(base_url, cookies, headers)
    logging.info(f"[post2] Challenge solved for {base_url}, full session cached.")

    return {
        "cookies": cookies,
        "headers": headers,
    }


def _do_post(post_url: str, json_body: dict, session: dict):
    """
    Make a JSON POST to post_url using the given session (userAgent + cookies).
    Returns (response_data, status_code, error_message).
    response_data is the parsed JSON if successful, or raw text otherwise.
    """
    cookies_list = session["cookies"]
    # Selenium returns cookies as list of dicts; requests needs name→value dict
    cookies_dict = {c["name"]: c["value"] for c in cookies_list}

    # Derive Origin / Referer from the base URL embedded in post_url
    from urllib.parse import urlparse
    parsed = urlparse(post_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    referer = origin + "/"

    headers = {
        "User-Agent": session["headers"].get("User-Agent", ""),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": referer,
    }

    try:
        resp = stdlib_requests.post(
            post_url,
            headers=headers,
            cookies=cookies_dict,
            json=json_body,
            timeout=30,
        )
        status_code = resp.status_code
        logging.info(f"[post2] POST {post_url} → HTTP {status_code}")
        try:
            return resp.json(), status_code, None
        except Exception:
            return resp.text, status_code, None
    except Exception as e:
        logging.error(f"[post2] Request error for {post_url}: {e}")
        return None, 0, str(e)


def _error_response(message: str, start_ts: int) -> V1ResponseBase:
    res = V1ResponseBase({})
    res.status = STATUS_ERROR
    res.message = message
    elapsed_sec = round((time.time() * 1000 - start_ts) / 1000)
    res.time_taken = f"{elapsed_sec} sec"
    return res
