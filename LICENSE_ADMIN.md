# OCTORA — License Administration Guide (for Sudeep, the seller)

This is how you generate and sell license keys for OCTORA.

## Honest note first

No desktop software is literally uncrackable — anyone skilled enough can patch
any program. What this system gives you is the **strongest practical protection
for a Python app**:

- **RSA-signed keys** — only a key signed by YOUR private key can activate.
- **Hardware-ID lock** — each key works on one machine only.
- **Expiry + trial + offline grace** — 7-day trial, license expiry, 3-day grace.
- **Tamper checks** — edited license files fail signature verification; clock
  rollback is detected.
- **Obfuscation-friendly** — freeze with PyInstaller and optionally run a
  bytecode obfuscator (e.g. pyarmor) over the bundle before shipping.

Pirates can still share one key per machine — that is what HWID locking limits:
one purchase = one machine.

## STRICT 1-PC-1-LICENSE POLICY (v1.1+)

**One license key = exactly ONE machine. No exceptions in the software.**

How it is enforced:
1. The key's payload contains the buyer's HWID, signed with your RSA private
   key (can't be forged or edited — signature check fails).
2. **Activation refuses** any key whose HWID doesn't match the machine it's
   being installed on, with the message:
   *"⛔ This license is bound to ANOTHER machine and cannot be activated here."*
3. **Every app start re-verifies** the signature AND the HWID match. If the
   `license.octalicense` file is copied to any other PC, the app starts in
   the activation screen with:
   *"⛔ This license is bound to ANOTHER machine and cannot be used here."*
4. Copying the config file or the whole data folder along with the license
   does NOT help — the HWID is recomputed from the current machine's
   hardware (Windows machine UUID / Linux machine-id / macOS platform UUID)
   on every launch.
5. Clock rollback to extend a license is detected (grace mode, not a free
   extension).

What this means for your sales:
- Tell buyers upfront: **1 purchase = 1 PC**. Put it on your sales page.
- If a buyer's PC dies / they buy a new PC: they send the NEW HWID, you
  re-run the `license` command (takes 10 seconds). Charge a re-issue fee or
  do it free once — your call, but decide the policy BEFORE selling.
- A leaked key is useless on any machine except the one it was issued for.

## One-time setup (on YOUR computer — never on a buyer's machine)

```bash
pip install cryptography
cd <OCTORA source folder>
python tools/keygen.py keypair
```

This creates `tools/seller_private.pem` — **BACK IT UP and NEVER share it.**
Anyone with this file can mint unlimited licenses.

> The ZIP you received already contains a working keypair whose public key is
> embedded in the app. A copy of the matching private key was delivered to you
> separately. For maximum security, generate your OWN keypair with the command
> above, paste the printed `PUBLIC_N` / `PUBLIC_E` into `octora/core/license.py`
> (replacing the existing values), and rebuild the .exe. Old keys stop working.

## Selling a license (the normal flow)

1. Buyer installs OCTORA and opens it. The **activation screen** shows their
   **HWID** (e.g. `8228bc2cf5a275a96ba3dd2dd588c74b`) and offers a 7-day trial.
2. Buyer pays you and sends you: **name, email, HWID**.
3. You run (on your machine):
   ```bash
   python tools/keygen.py license --name "Buyer Name" --email buyer@mail.com \
       --hwid 8228bc2cf5a275a96ba3dd2dd588c74b --days 365 --out buyer.octalicense
   ```
   `--days` = license length. Use `--days 9999` for "lifetime".
4. Send `buyer.octalicense` to the buyer (email / WhatsApp / anything).
5. Buyer clicks **"Enter / change license key"** (activation screen or
   Settings → License), pastes the file contents → **Activated**.

## Useful commands

```bash
python tools/keygen.py hwid        # print this machine's HWID (for testing)
python tools/keygen.py license --help
```

## Pricing / policy ideas

- Trial: 7 days, full features (built in).
- License file includes the buyer's name/email — show it on receipts.
- Offline grace: if a license expires, the app keeps working 3 more days and
  warns — no angry "it just stopped" moments for paying customers.
- Lost key: just re-run the `license` command for the same HWID (free) or
  charge a re-issue fee — your call.

## Files

| File | Keep secret? |
|---|---|
| `tools/seller_private.pem` | **YES — never ship, never share** |
| `*.octalicense` (per buyer) | No (locked to their HWID anyway) |
| `octora/core/license.py` (`PUBLIC_N`/`PUBLIC_E`) | No — public by design |

## If a key leaks

A leaked key only works on the machine whose HWID it was issued for, so damage
is limited. For a new app version you can rotate the keypair (new `keypair`
command → new public key in `license.py` → rebuild) which invalidates every
old key at once.
