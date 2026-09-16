#!/usr/bin/env python3
"""Sign the OCTORA auto-update manifest with the seller's private key.

The desktop app verifies this RSA signature (embedded public key) before
offering ANY update, so a compromised website alone cannot push malware to
users. The private key never leaves the seller's machine / server env.

Usage:
    python tools/sign_manifest.py --version 1.4.1 \\
        --url https://github.com/octora-app/OCTORA/releases/latest/download/OCTORA-Setup.exe \\
        --sha256 <hex of the installer> \\
        --changelog "Bug fixes and improvements." \\
        [--mandatory] --out ../../octora-site/releases/latest.json

The PEM is read from OCTORA_SELLER_PEM (env) or --key path.
"""
import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--changelog", default="")
    ap.add_argument("--mandatory", action="store_true")
    ap.add_argument("--key", default="", help="path to seller private key PEM")
    ap.add_argument("--out", required=True, help="where to write latest.json")
    a = ap.parse_args()

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    pem = a.key or os.environ.get("OCTORA_SELLER_PEM", "")
    if a.key:
        data = open(a.key, "rb").read()
    elif pem.strip():
        data = pem.encode()
    else:
        print("ERROR: seller key missing — pass --key or set OCTORA_SELLER_PEM",
              file=sys.stderr)
        return 2
    key = serialization.load_pem_private_key(data, password=None)

    manifest = {
        "version": a.version,
        "download_url": a.url,
        "changelog": a.changelog,
        "mandatory": bool(a.mandatory),
        "sha256": a.sha256.strip().lower(),
    }
    canonical = json.dumps(manifest, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    sig = key.sign(canonical, padding.PKCS1v15(), hashes.SHA256())
    manifest["signature"] = base64.b64encode(sig).decode()

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"signed manifest v{a.version} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
