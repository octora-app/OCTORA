#!/usr/bin/env python3
"""OCTORA seller-side license key generator. KEEP seller_private.pem SECRET.

Requires: pip install cryptography   (seller machine only — never shipped in the app)

Workflow for Sudeep (see LICENSE_ADMIN.md for the full guide):
  1. python tools/keygen.py keypair        # once: creates seller_private.pem
  2. Paste the printed PUBLIC_N / PUBLIC_E into octora/core/license.py, rebuild the app.
  3. Buyer sends you their HWID (shown on the app's activation screen).
  4. python tools/keygen.py license --name "Buyer Name" --email buyer@mail.com \\
         --hwid <HWID> --days 365 --out buyer.octalicense
  5. Send buyer.octalicense to the buyer. They load it in the app -> activated.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE_KEY_FILE = HERE / "seller_private.pem"

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
except ImportError:
    print("ERROR: 'cryptography' package required on the seller machine.\n"
          "Install it with:  pip install cryptography")
    sys.exit(1)


def cmd_keypair(_args):
    if PRIVATE_KEY_FILE.exists():
        print(f"Refusing to overwrite existing {PRIVATE_KEY_FILE}")
        sys.exit(1)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    PRIVATE_KEY_FILE.write_bytes(pem)
    os.chmod(PRIVATE_KEY_FILE, 0o600)
    pub = key.public_key().public_numbers()
    print("Keypair created. PRIVATE key saved to:", PRIVATE_KEY_FILE)
    print(">>> Paste this block into octora/core/license.py (replace the placeholders):\n")
    print(f"PUBLIC_N = {pub.n}")
    print(f"PUBLIC_E = {pub.e}")


def _load_private():
    if not PRIVATE_KEY_FILE.exists():
        print(f"No {PRIVATE_KEY_FILE} — run 'keypair' first.")
        sys.exit(1)
    return serialization.load_pem_private_key(PRIVATE_KEY_FILE.read_bytes(), password=None)


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def cmd_license(args):
    key = _load_private()
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "product": "OCTORA",
        "name": args.name,
        "email": args.email,
        "hwid": args.hwid.strip().lower(),
        "issued": now.strftime("%Y-%m-%d"),
        "expires": (now + timedelta(days=args.days)).strftime("%Y-%m-%d"),
        "features": ["full"],
    }
    sig = key.sign(_canonical(payload), padding.PKCS1v15(), hashes.SHA256())
    envelope = {"payload": payload, "sig": base64.b64encode(sig).decode()}
    body = base64.b64encode(json.dumps(envelope).encode()).decode()
    armored = ("-----BEGIN OCTORA LICENSE-----\n" + "\n".join(
        body[i:i + 64] for i in range(0, len(body), 64)) +
        "\n-----END OCTORA LICENSE-----\n")
    out = Path(args.out)
    out.write_text(armored, encoding="utf-8")
    print(f"License written: {out}")
    print(f"  Licensed to : {args.name} <{args.email}>")
    print(f"  HWID        : {args.hwid}")
    print(f"  Expires     : {payload['expires']} ({args.days} days)")
    print("Send this file to the buyer. They activate via File/Activation screen.")


def cmd_hwid(_args):
    import platform
    import uuid
    raw = f"{platform.system()}|{platform.node()}|{uuid.getnode()}"
    print(hashlib.sha256(raw.encode()).hexdigest()[:32])


def main():
    ap = argparse.ArgumentParser(description="OCTORA license key generator (seller side)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keypair", help="Generate seller RSA keypair (run once)")
    sub.add_parser("hwid", help="Print this machine's HWID (for testing)")
    lp = sub.add_parser("license", help="Issue a signed license file")
    lp.add_argument("--name", required=True)
    lp.add_argument("--email", required=True)
    lp.add_argument("--hwid", required=True, help="Buyer's HWID from their activation screen")
    lp.add_argument("--days", type=int, default=365)
    lp.add_argument("--out", required=True, help="Output .octalicense file")
    args = ap.parse_args()
    {"keypair": cmd_keypair, "hwid": cmd_hwid, "license": cmd_license}[args.cmd](args)


if __name__ == "__main__":
    main()
