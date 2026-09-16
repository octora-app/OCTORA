# 🔐 SELLER_SETUP.md — one-time setup BEFORE you sell OCTORA

**For Sudeep (the seller) only. Never ship this file's contents to customers.**

Your customers NEVER touch API keys. You register **one** Google Cloud project,
**one** Meta app and **one** TikTok app, paste the credentials into
`octora/seller_config.json` once, then build the ZIP/EXE and sell it.
Customers just click **Connect to YouTube / Google Drive / Instagram…** and
sign in with their own accounts.

---

## A. Google — YouTube + Drive (the important one)

1. Go to <https://console.cloud.google.com> → create a **new project**
   (e.g. `octora-prod`).
2. **APIs & Services → Library** → enable:
   - **YouTube Data API v3**
   - **Google Drive API**
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - Fill app name (`OCTORA`), support email, developer email.
   - **Scopes → Add**: `.../auth/youtube.upload`, `.../auth/drive.file`,
     `openid`, `email`.
   - **Test users**: while in *Testing* mode, add your own Gmail here.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app** → Create.
   - Copy the **Client ID** and **Client secret**.
5. Open `octora/seller_config.json` in this folder and paste:
   ```json
   "google": {
     "client_id": "YOUR_ID.apps.googleusercontent.com",
     "client_secret": "YOUR_SECRET"
   }
   ```
6. Rebuild the ZIP / EXE **after** pasting (the file is bundled into the build).

### ⚠️ Honest Google notes (read before selling)
- **Testing mode ≤ 100 users.** Every customer counts as a user. For public
  sale you must switch the consent screen to **Production** and pass
  **Google's verification** — `youtube.upload` is a **sensitive scope** and
  the review is strict (can take days–weeks; you must justify why you need
  upload access, show a demo video, privacy policy URL, etc.). Until verified,
  users see an "unverified app" warning screen (they can still click through
  in Testing mode).
- **YouTube quota:** default **10,000 units/day per project**; one video
  upload costs **1,600 units → ≈ 6 uploads/day across ALL your customers
  combined** on this project. If you sell widely, request a **quota extension**
  in the Cloud Console (free, needs justification). Drive API quotas are
  generous and rarely a problem.
- **Key safety:** if `seller_config.json` ever leaks, create a new OAuth
  client, update the JSON, rebuild, re-ship. Never commit it to public git.

## B. Meta — Instagram + Facebook

1. Go to <https://developers.facebook.com> → **Create App** (type: Business).
2. Add products: **Facebook Login** and **Instagram Graph API**.
   (Facebook Login settings → Valid OAuth Redirect URIs: you don't need to
   add anything — OCTORA uses `http://127.0.0.1:<random-port>/` loopback,
   which Meta allows for desktop apps.)
3. **App Settings → Basic** → copy **App ID** and **App secret** →
   paste into `seller_config.json` under `"meta"`.
4. Rebuild after pasting.

### ⚠️ Honest Meta notes
- In **Development** mode only *test users* (added in App Roles) can log in.
  To sell to the public: switch the app to **Live** and pass **App Review**
  for `instagram_basic`, `instagram_content_publish`, `pages_manage_posts`
  (Meta reviews each permission; business verification may be required).
- Customers need a **Facebook Page** + a **Business/Creator Instagram**
  linked to it — the app tells them this on the Platforms screen.

## C. TikTok

1. Go to <https://developers.tiktok.com> → create an app → add the
   **Content Posting API** product → copy **Client key** + **Client secret**
   → paste into `seller_config.json` under `"tiktok"`.
2. Rebuild after pasting.

### ⚠️ Honest TikTok notes
- TikTok **audits** every app before Content Posting API works in production
  (can take days). OAuth login works regardless; the app reports the audit
  status honestly instead of faking posts.

## D. After filling the JSON

1. `python -m py_compile` everything (or just run the QA below).
2. Rebuild: `python build_exe.py --onedir` **on a Windows PC**
   (PyInstaller can't cross-compile), or re-zip the folder for ZIP sales.
3. `seller_config.json` is bundled automatically (`--add-data` is already in
   `build_exe.py`). Verify: the built app's Platforms screen must NOT show
   "SELLER SETUP NEEDED".
4. Sell licenses with `tools/keygen.py` — see `LICENSE_ADMIN.md`.
   Back up `OCTORA-SELLER-PRIVATE-KEY_DO-NOT-SHARE.pem` offline.

## E. Quick QA before every release

```bat
python -m compileall -q octora tools main.py
set OCTORA_SMOKE_TEST=12 && set QT_QPA_PLATFORM=offscreen && python main.py
```
Must exit 0 with no tracebacks. Open the Platforms screen and confirm the
Connect buttons are enabled (seller config detected).
