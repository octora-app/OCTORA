# 🐙 OCTORA v1.4 — Automate Beyond Limits
**Powered by Rouqil Tech** · *Human ideas. Amplified.*

Desktop automation software for **YouTube Shorts**, **Instagram Reels**,
**TikTok** & **Facebook Reels** auto-publishing: campaigns, Drive sync, IST
scheduler, upload engine with retries, and a live monitor dashboard — all in
a Doc Ock-inspired dark interface.

> **No API keys. Ever.** Click **Connect to YouTube** / **Connect to Google
> Drive** on the Platforms screen, sign in with your own account in the
> browser, done. Your tokens stay on your machine only.

---

## 🆕 What's new in v1.4

- **🎁 1-day free trial** — download, try every feature for a day, no payment
  needed. After the trial, the app tells you a subscription is required.
- **💰 Buy with USDT (TRC-20), auto-activated** — pick 7-Day (10 USDT),
  30-Day (30 USDT) or Lifetime (100 USDT), send USDT to the seller's TRC-20
  address, paste your transaction ID in the app — the payment is verified
  on-chain automatically and your license activates instantly. No waiting.
- **🔄 One-click auto-updates** — when a new version ships, OCTORA shows a
  popup with what's new. One click downloads and installs it, then restarts
  the app. You never handle update files manually.
- **🔒 1-PC-1-license, hardened** — RSA-signed keys bound to your machine
  (checked on every launch), server-side revocation, clock-tamper detection,
  and optional PyArmor obfuscation at build time (`build_exe.py --obfuscate`).

## 🆕 What's new in v1.3

- **📡 Seller admin panel (optional, free to host)** — the seller can now see
  all customers in one dashboard: connected channels, subscriber counts,
  upload results, last-active. Ships in `octora-admin/` with a step-by-step
  free-hosting guide (`ADMIN_SETUP.md`). Needs a server URL from your seller
  to do anything — otherwise it's completely inert.
- **🔒 Your privacy, your choice** — on first run OCTORA asks once whether it
  may send anonymous usage stats (app version, connected platforms, upload
  counts — **never** your videos or files). Decline, and **zero** network
  calls are ever made. Toggle anytime in Settings → Seller connection, where
  you can also read the full `PRIVACY.md`.
- **🌐 Online license activation** — alternative to the license file: paste
  the key your seller emailed you and activate against the seller's server.
  File activation still works as before.

## 🆕 What's new in v1.2

- **📁 Zero-setup Google Drive folders** — the moment you connect Google,
  OCTORA creates an `OCTORA` folder in your Drive automatically, plus one
  subfolder per campaign (`OCTORA/<CampaignName>`). Every upload lands in
  the right folder with **zero setup** from you. The Drive Sync screen shows
  a clickable link to your folder.
- **🎯 Automatic SEO metadata engine (rules-based, no AI claims)** — every
  upload gets its best title, description/tags, and caption automatically:
  - YouTube Shorts: keyword-first title (≤100 chars), rich description, tags.
  - IG Reels / TikTok / FB Reels: hook-first caption + the right hashtag count.
  - The keyword comes from the **video filename** (`morning-routine_014.mp4`
    → "Morning Routine", episode 14); niche keyword banks cover tech,
    fitness, cooking, finance, motivation, comedy, education, fashion,
    travel, gaming.
  - Per-campaign **templates** with variables (`{keyword}`, `{episode}`,
    `{niche}`, `{date}`, `{platform}` …), live preview with title-length
    counter and best-practice warnings.
  - Scheduler lets you **override** title/description/tags/caption per video;
    overrides always win, blanks always auto-generate.
  - Try it in **Tools → SEO Metadata Lab** before you go live.

---

## 🚀 How to run (Windows — 3 steps, no technical knowledge needed)

1. **Install Python**: download from <https://www.python.org/downloads/> (3.10 or newer).
   ⚠️ On the first install screen, tick **"Add python.exe to PATH"**, then finish install.
2. **Unzip** `OCTORA-v1.2.zip` anywhere (e.g. Desktop).
3. **Double-click `run.bat`**.

That's it. First launch creates everything automatically and installs the free
libraries it needs (internet required once). The app opens with **demo data**
so you can see it working immediately.

On Mac/Linux: `chmod +x run.sh && ./run.sh`

## 🔑 Going LIVE — just click Connect (no keys needed)

**Demo mode (default ON)** simulates the whole pipeline so you can explore
safely. When you're ready for real posting:

1. Open the **🔌 Platforms** screen (sidebar).
2. Click **▶ Connect to YouTube** → your browser opens → sign in with the
   Google account that owns your channel → approve → done.
   One sign-in also powers **☁ Connect to Google Drive** (cloud backup).
3. Click **📸 Connect Instagram** / **📘 Connect Facebook** / **🎵 Connect TikTok**
   the same way.

That's the whole setup. The app shows **who you're signed in as**
(`Connected as you@gmail.com`) and a **Disconnect** button wipes your tokens
from the machine.

**What actually posts in v1.2:**
- **Google Drive upload — REAL** (resumable upload, OAuth).
- **YouTube Shorts upload — REAL** (resumable upload, OAuth).
- **Instagram / TikTok / Facebook** — sign-in works; direct posting calls are
  honest stubs in v1.2 and say exactly what's missing (Meta needs a public
  video URL + app review; TikTok needs its Content Posting audit).

> **OCTORA will never fake a real post.** Anything not yet implemented says so
> explicitly in the UI and logs.

**FAQ**
- *Do I need API keys?* No. The seller's registered app handles that —
  you only sign in.
- *Does OCTORA see my password?* No. You type it only on Google/Meta/TikTok's
  own sign-in pages in your browser.
- *Can I use it on 2 PCs?* Yes — connect on each; licenses are per-machine.

## 🖥 What you get

| Screen | What it does |
|---|---|
| **Dashboard** | Live operations: stat tiles, 6-stage pipeline cards (Download → Fetch → Render → Drive → Publish → Cleanup) driven by real worker threads, today's IST scheduler timeline, error/storage/queue status bar |
| **Campaigns** | Create/edit/delete campaigns: platform, source folder, daily IST time, caption template |
| **Scheduler** | Add/edit/cancel scheduled posts; due posts flow into the upload queue automatically |
| **Drive Sync** | Drop videos into the watched folder → auto-imported with duplicate detection + validation; Google Drive upload status + retry |
| **Upload Engine** | Real queue: pause/resume/cancel, exponential-backoff retries, dead-letter list, priorities, CSV export |
| **Platforms** | One-click Connect buttons: YouTube, Google Drive, Instagram, Facebook, TikTok — live status, connected account, Disconnect |
| **Analytics** | Charts from your database: uploads/day, per-platform, success rate, best posting hours |
| **Tools** | Caption + hashtag generator, best-time-to-post IST heatmap, bulk video import, URL download queue |
| **Logs** | Live log viewer (every worker writes here) |
| **Settings** | Demo/Live toggle, pipeline automation (auto-delete/keep-backup), folders, license, accent color |

**Extras:** keyboard shortcuts (`Ctrl+1…0` switch screens, `Ctrl+R` refresh),
minimize-to-tray with notifications, video validation (ffprobe if installed,
otherwise size heuristic), queue priorities, RSA-signed licensing with 7-day trial.

## 🔐 Licensing

First launch: start the **free 7-day trial** or paste a license key. Trial =
full features. Licenses are RSA-signed and locked to one machine (HWID).
Sellers: see **LICENSE_ADMIN.md** for the key generator (`tools/keygen.py`).

## 💻 Building the Windows EXE (on a Windows PC — seller step)

PyInstaller **cannot cross-compile** — the `.exe` must be built on Windows.
This ZIP contains **Python source only** — no `.exe`. Sellers: fill
`octora/seller_config.json` first (see **SELLER_SETUP.md**), then on Windows:

```bat
cd OCTORA-v1.2
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build_exe.py --onedir
```
Result: `dist\OCTORA\OCTORA.exe` (run from that folder).
Single-file version: `python build_exe.py --onefile` → `dist\OCTORA.exe`.

**Installer:** install [Inno Setup 6](https://jrsoftware.org/isinfo.php), open
`installer.iss`, press Compile → `Output\OCTORA-Setup-1.1.0.exe`.

## 📁 Your data

Everything lives locally next to the app:
- Windows: `%APPDATA%\OCTORA\` (database `octora.db`, `config.json`, logs, `drive\`, `assets\`)
- Mac/Linux: `~/.octora/`
- Override with the `OCTORA_DATA_DIR` environment variable.

## 🛠 Manual run (developers)

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

Headless smoke test: `QT_QPA_PLATFORM=offscreen OCTORA_SMOKE_TEST=8 python main.py`

---
© 2026 Rouqil Tech — DISCIPLINE CREATES FREEDOM.
