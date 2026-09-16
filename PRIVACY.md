# PRIVACY.md — what OCTORA's optional telemetry collects (plain language)

> Show this to every customer BEFORE they enable telemetry (first-run dialog
> and Settings). Required for Google API policy compliance. No hidden data
> collection, ever.

## In one line
If you allow it, the app sends a tiny status ping to the seller's server
every ~6 hours. Nothing else. You can turn it off anytime in Settings.

## Exactly what is sent (each ping)
- **App version** (e.g. "1.3")
- **Which platforms you connected** — e.g. "YouTube", "Instagram" — plus the
  channel/page **name** and **subscriber count** if available
- **Upload counters** — how many videos posted in total, and today
- **A hardware fingerprint hash** (`hwid_hash`) — a one-way SHA-256 hash used
  only to tell your PC apart from another PC for licensing. It **cannot** be
  reversed to identify your hardware, and the raw hardware ID never leaves
  your PC.
- **Timestamp** of the ping

## What is NEVER sent
- Your videos, thumbnails, or any file contents
- File names or folder paths on your PC
- Your Google/Meta/TikTok passwords or access tokens
- Browsing history or anything outside the app

## Why it exists
1. **License protection** — one license = one PC (your purchase terms).
2. **Support** — if something breaks, support can see your connected
   channels and recent upload results and help faster.
3. **Product stats** — the seller sees how many users are active.

## Your control
- First launch asks for permission — **default is OFF**.
- Settings → uncheck telemetry → sending stops immediately.
- Server keeps heartbeat history for 120 days, then it is deleted.

## Who sees it
Only the software seller (Sudeep / Rouqil Tech) on their private admin
panel. Data is never sold or shared with third parties.

Questions: Telegram **@batmanjaatwhop**
