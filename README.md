### PATCH VERSION OF FLARESOLVER

[Original FlareSolverr](https://github.com/FlareSolverr/FlareSolverr)

Added a feature to do a post request to a website with Cloudflare Turnstile / challenge protection — solving the CF challenge automatically, caching the session, then making the JSON POST from within the container.

---

## API Documentation

All endpoints are exposed on `http://localhost:8191` by default.

---

### `GET /`

Returns the server status and current User-Agent.

**Response**
```json
{
  "msg": "FlareSolverr is ready!",
  "version": "3.x.x",
  "userAgent": "Mozilla/5.0 ..."
}
```

---

### `GET /health`

Healthcheck endpoint.

**Response**
```json
{ "status": "ok" }
```

---

### `POST /v1`

Main command endpoint. All commands are routed through this endpoint via the `cmd` field.

**Common request fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `cmd` | string | ✅ | Command to execute (see below) |
| `maxTimeout` | int (ms) | ❌ | Max wait time in milliseconds (default: 60000) |
| `session` | string | ❌ | Named session ID to reuse a persistent browser |
| `session_ttl_minutes` | int | ❌ | TTL for the named session |
| `proxy` | object | ❌ | `{ "url": "...", "username": "...", "password": "..." }` |
| `cookies` | list | ❌ | Cookies to inject before the request |

---

#### `request.get`

Fetches a URL, solving any Cloudflare challenge automatically.

**Additional fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | ✅ | URL to fetch |
| `returnOnlyCookies` | bool | ❌ | Return only cookies, skip response body |
| `returnScreenshot` | bool | ❌ | Include a base64 screenshot in the response |
| `waitInSeconds` | int | ❌ | Wait N seconds before returning |
| `disableMedia` | bool | ❌ | Block images, CSS, and fonts to speed up load |
| `tabs_till_verify` | int | ❌ | Number of Tab presses to reach the Turnstile checkbox |

**Request**
```json
{
  "cmd": "request.get",
  "url": "https://example.com",
  "maxTimeout": 60000
}
```

**Response**
```json
{
  "status": "ok",
  "message": "Challenge solved!",
  "startTimestamp": 1720000000000,
  "endTimestamp":   1720000005000,
  "version": "3.x.x",
  "solution": {
    "url": "https://example.com/",
    "status": 200,
    "headers": {},
    "response": "<html>...</html>",
    "cookies": [{ "name": "cf_clearance", "value": "...", ... }],
    "userAgent": "Mozilla/5.0 ...",
    "turnstile_token": null
  }
}
```

---

#### `request.post`

Submits a form POST through the browser (URL-encoded form data), solving any CF challenge.

**Additional fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | ✅ | Target URL |
| `postData` | string | ✅ | URL-encoded form body, e.g. `field1=value1&field2=value2` |

**Request**
```json
{
  "cmd": "request.post",
  "url": "https://example.com/login",
  "postData": "username=foo&password=bar",
  "maxTimeout": 60000
}
```

**Response** — same shape as `request.get`.

---

#### `request.post2` ⭐ (Patch Feature)

Solves the Cloudflare challenge on a site's home page, caches the resulting session (cookies + User-Agent), then makes a **JSON POST** to any sub-endpoint of that site — all from within the container so the IP matches the one that passed the challenge.

**Caching behaviour**
- First call → browser opens, solves CF challenge, session saved to `/config/post2_db.json`.
- Subsequent calls → session reused (no browser launch, fast path).
- On `403` → session evicted, challenge re-solved once, POST retried. If still `403`, returns the error.

**Additional fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `base_url` | string | ✅ | Site home URL where the CF challenge is solved (e.g. `https://example.com`) |
| `post_endpoint` | string | ✅ | Path/endpoint to POST to, relative to `base_url` (e.g. `api/data`) |
| `post_json_body` | dict \| string | ✅ | JSON body for the POST — either a dict or a JSON-encoded string |

**Request**
```json
{
  "cmd": "request.post2",
  "base_url": "https://example.com",
  "post_endpoint": "api/data",
  "post_json_body": { "key": "value" }
}
```

**Success Response**
```json
{
  "status": "ok",
  "message": "OK",
  "startTimestamp": 1720000000000,
  "endTimestamp":   1720000003000,
  "version": "3.x.x",
  "time_taken": "3 sec",
  "target_url_response": {
    "status_code": 200,
    "body": { "result": "..." },
    "error": null
  }
}
```

**Error Response**
```json
{
  "status": "error",
  "message": "Failed to solve Cloudflare challenge for https://example.com/.",
  "time_taken": "5 sec",
  "target_url_response": {
    "status_code": 403,
    "body": null,
    "error": "..."
  }
}
```

---

#### `sessions.create`

Creates (or retrieves) a named persistent browser session.

**Request**
```json
{
  "cmd": "sessions.create",
  "session": "my-session"
}
```

**Response**
```json
{
  "status": "ok",
  "message": "Session created successfully.",
  "session": "my-session"
}
```

---

#### `sessions.list`

Lists all active session IDs.

**Request**
```json
{ "cmd": "sessions.list" }
```

**Response**
```json
{
  "status": "ok",
  "message": "",
  "sessions": ["my-session", "other-session"]
}
```

---

#### `sessions.destroy`

Destroys a named session and closes its browser.

**Request**
```json
{
  "cmd": "sessions.destroy",
  "session": "my-session"
}
```

**Response**
```json
{
  "status": "ok",
  "message": "The session has been removed."
}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8191` | Server port |
| `LOG_LEVEL` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |
| `LOG_FILE` | — | Optional path to write log file |
| `LOG_HTML` | `false` | Log full page HTML in debug mode |
| `HEADLESS` | `true` | Run Chrome in headless mode |
| `DISABLE_MEDIA` | `false` | Block images/CSS/fonts globally |
| `PROXY_URL` | — | Default proxy URL for all requests |
| `PROXY_USERNAME` | — | Proxy username |
| `PROXY_PASSWORD` | — | Proxy password |
| `MAX_BROWSERS` | `3` | Max simultaneous headless Chrome instances for `request.post2` |
| `CF_SOLVE_TIMEOUT_MS` | `180000` | Timeout (ms) for CF challenge solve in `request.post2` (default 3 min) |
| `POST2_DB_PATH` | `/config/post2_db.json` | Path to the session cache file for `request.post2` |
