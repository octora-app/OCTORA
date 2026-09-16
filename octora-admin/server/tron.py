"""Verify USDT (TRC-20) payments on the Tron blockchain via TronGrid.

Strict verification pipeline (a license is issued ONLY if every check passes):
1. TXID format must be 64 hex chars.
2. POST /wallet/gettransactioninfobyid -> the transaction must exist and its
   receipt.result must be "SUCCESS" (rejects failed / reverted transfers).
3. GET /v1/transactions/{txid}/events -> find a Transfer event on the USDT
   (TRC-20) contract whose `to` decodes to the seller address and whose value
   is >= the plan price. (The plain /v1/transactions/{hash} endpoint is
   unreliable for contract txs — verified 2026-09-16 against live mainnet data.)
4. Finality: the payment must be at least OCTORA_MIN_TX_AGE_SECONDS old
   (default 90s ~ 30 Tron blocks; Tron's 3s DPoS blocks make older
   transactions irreversible for all practical purposes).

Tron event addresses come as 0x-hex; they are converted to base58check for
comparison with the seller address. Free, no API key required for the volumes
a new product sees (an optional TRONGRID_API_KEY raises the rate limit).
"""
import hashlib
import json
import urllib.request

from . import config

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def hex_to_base58check(hex_addr: str) -> str:
    """Convert a Tron hex address (with or without 0x) to base58check (T...)."""
    h = hex_addr.strip().lower()
    if h.startswith("0x"):
        h = h[2:]
    if len(h) == 40:          # missing the 0x41 Tron prefix -> add it
        h = "41" + h
    if len(h) != 42:
        raise ValueError(f"bad Tron address hex: {hex_addr!r}")
    raw = bytes.fromhex(h)
    checksum = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    data = raw + checksum
    num = int.from_bytes(data, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58[rem] + out
    # leading zero bytes -> leading '1's
    pad = 0
    for b in data:
        if b == 0:
            pad += 1
        else:
            break
    return "1" * pad + out


def _get(path: str, retries: int = 2) -> dict:
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(
                config.TRONGRID_API + path, headers={"Accept": "application/json"})
            if config.TRONGRID_API_KEY:
                req.add_header("TRON-PRO-API-KEY", config.TRONGRID_API_KEY)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - transient network hiccup, retry
            last = e
    raise last


def _post(path: str, payload: dict, retries: int = 2) -> dict:
    body = json.dumps(payload).encode("utf-8")
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(
                config.TRONGRID_API + path, data=body,
                headers={"Accept": "application/json", "Content-Type": "application/json"})
            if config.TRONGRID_API_KEY:
                req.add_header("TRON-PRO-API-KEY", config.TRONGRID_API_KEY)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - transient network hiccup, retry
            last = e
    raise last


def _tx_age_seconds(block_timestamp_ms) -> float:
    import time
    try:
        return time.time() - int(block_timestamp_ms) / 1000.0
    except (TypeError, ValueError):
        raise ValueError("Could not determine the transaction's age.")


def find_usdt_payment(txid: str, min_usdt: float) -> dict:
    """Locate a confirmed USDT (TRC-20) transfer to the seller in `txid`.

    Returns {"amount_usdt", "from_address", "timestamp_ms", "age_seconds"}.
    Raises ValueError with a user-friendly message when anything is off.
    """
    txid = (txid or "").strip().lower()
    if len(txid) != 64 or any(c not in "0123456789abcdef" for c in txid):
        raise ValueError(
            "That doesn't look like a Tron transaction ID "
            "(it should be 64 hex characters).")

    # --- step 1: transaction must exist and have SUCCEEDED on-chain ---
    try:
        info = _post("/wallet/gettransactioninfobyid", {"value": txid})
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            f"Could not reach the Tron network to check that transaction: {e}")
    if not info or not info.get("id"):
        raise ValueError(
            "Transaction not found on the Tron network yet — "
            "wait a minute after sending and try again.")
    receipt = info.get("receipt") or {}
    if receipt.get("result") != "SUCCESS":
        raise ValueError(
            "That transaction FAILED on-chain, so no payment was received.")

    # --- step 2: finality — the payment must be old enough to be irreversible.
    # Tron makes a block every ~3s under DPoS; a 90s-old transaction is final
    # for all practical purposes (this also defeats re-org double-spends).
    tx_time = info.get("blockTimeStamp")
    age_s = _tx_age_seconds(tx_time)
    if age_s < config.MIN_TX_AGE_SECONDS:
        raise ValueError(
            f"Payment is on-chain but too fresh ({int(age_s)}s old). "
            f"Wait about a minute and try again.")

    # --- step 3: find the USDT Transfer event to the seller ---
    try:
        events = _get(f"/v1/transactions/{txid}/events?limit=25")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not read the transaction's transfer details: {e}")
    seller = config.SELLER_USDT_TRC20
    for ev in events.get("data") or []:
        if ev.get("event_name") != "Transfer":
            continue
        if (ev.get("contract_address") or "") != config.USDT_TRC20_CONTRACT:
            continue  # not USDT — ignore other tokens in the same tx
        res = ev.get("result") or {}
        try:
            to_addr = hex_to_base58check(res.get("to", ""))
            from_addr = hex_to_base58check(res.get("from", ""))
        except ValueError:
            continue
        if to_addr != seller:
            continue  # USDT went somewhere else, not to us
        try:
            amount = int(str(res.get("value", "0"))) / 1_000_000  # USDT: 6 decimals
        except (TypeError, ValueError):
            continue
        if amount + 1e-9 >= min_usdt:
            return {"amount_usdt": amount,
                    "from_address": from_addr,
                    "timestamp_ms": ev.get("block_timestamp"),
                    "age_seconds": int(age_s)}
    raise ValueError(
        "No matching USDT (TRC-20) payment to the seller address was found in "
        "that transaction. Double-check the TXID, the exact amount, and that "
        "you sent on the TRC-20 (Tron) network.")
