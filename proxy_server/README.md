# 3proxy Windows Setup Guide

This guide helps you set up your home PC as a SOCKS5 proxy server, allowing
your Docker container to route Chrome traffic through your **residential IP**.

## Why?

Cloudflare assigns a low "trust score" to datacenter IPs (AWS, Azure, VPS providers),
triggering interactive Turnstile challenges. Your home ISP IP has a high trust score,
so Cloudflare will auto-pass the challenge (invisible mode).

---

## Quick Setup

### 1. Download 3proxy

Download the latest Windows binary from:
**https://3proxy.ru/download/stable/**

Extract to `C:\3proxy\`

### 2. Create Config File

Copy `3proxy.cfg.example` from this directory to `C:\3proxy\3proxy.cfg`

Edit the file and set:
- `YOUR_USERNAME` → your chosen proxy username
- `YOUR_PASSWORD` → your chosen proxy password
- `YOUR_LOCAL_IP` → your PC's LAN IP (find with `ipconfig`, e.g., `192.168.1.100`)

### 3. Open Windows Firewall

1. Open **Windows Defender Firewall with Advanced Security**
2. Click **Inbound Rules** → **New Rule...**
3. Select **Port** → **TCP** → **1080**
4. Allow the connection
5. Name it: `3proxy SOCKS5`

### 4. Start the Proxy

Open Command Prompt **as Administrator**:

```cmd
cd C:\3proxy
3proxy.exe 3proxy.cfg
```

To run as a background service:
```cmd
3proxy.exe --install C:\3proxy\3proxy.cfg
net start 3proxy
```

### 5. Find Your Public IP

Go to https://whatismyip.com and note your **public IPv4 address**.

### 6. Port Forwarding (if Docker is remote)

If your Docker container is on a **remote VPS** (not on your home PC):

1. Log into your router admin panel (usually `192.168.1.1`)
2. Find **Port Forwarding** settings
3. Forward external port `1080` → internal IP `YOUR_LOCAL_IP` port `1080` (TCP)
4. Your proxy is now accessible at `YOUR_PUBLIC_IP:1080`

If Docker runs **on the same PC**, use `host.docker.internal:1080` instead.

### 7. Configure the Bot

Add to your `.env` file:

```bash
# If Docker is remote (VPS):
PROXY_URL=socks5://YOUR_USERNAME:YOUR_PASSWORD@YOUR_PUBLIC_IP:1080

# If Docker is on the same PC:
PROXY_URL=socks5://YOUR_USERNAME:YOUR_PASSWORD@host.docker.internal:1080
```

---

## Testing

Verify the proxy is working from inside Docker:

```bash
docker exec -it botservice python -c "
import requests
r = requests.get('https://httpbin.org/ip', proxies={
    'https': 'socks5h://USER:PASS@host.docker.internal:1080'
})
print(r.json())
"
```

You should see your **home IP address**, not the VPS IP.

---

## Security Tips

- **Always use authentication** (`auth strong` in config)
- **Don't share your proxy credentials**
- **Consider SSH tunneling** for extra security (see below)

### Alternative: SSH Tunnel (more secure)

Instead of exposing port 1080 publicly, create an SSH tunnel:

```bash
# On your VPS/Docker host:
ssh -D 1080 -N -f user@YOUR_HOME_IP

# Then set:
PROXY_URL=socks5://127.0.0.1:1080
```

This encrypts all traffic and doesn't require opening firewall ports.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Connection refused | Check firewall rule; ensure 3proxy is running |
| Timeout | Check port forwarding on router |
| Auth failed | Verify username/password in `3proxy.cfg` |
| Wrong IP shown | Ensure `socks5h://` (with `h`) for DNS resolution through proxy |
