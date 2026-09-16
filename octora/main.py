"""OCTORA entry point."""
import os
import sys

from PyQt6.QtWidgets import QApplication

from octora.core.config import Config
from octora.core.database import Database
from octora.core.engine import Engine
from octora.core.license import LicenseManager
from octora.core.logger import get_logger
from octora.ui import theme
from octora.ui.activation import ActivationDialog
from octora.ui.main_window import MainWindow, AppContext


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OCTORA")
    app.setOrganizationName("Rouqil Tech")
    cfg = Config()
    log = get_logger("octora")

    # ---- licensing gate (trial / license / activation) ----
    lm = LicenseManager(cfg)
    # Background one-trial-per-PC sync: registers offline-started trials and
    # revokes trials re-started after the local app data was wiped. Daemon
    # thread — never blocks startup, never raises.
    lm.sync_trial_with_server()
    if not ActivationDialog.ensure_licensed(lm):
        log.info("activation declined — exiting")
        return 0
    st = lm.status()
    if st["mode"] != "licensed":
        log.info("license mode: %s (%s)", st["mode"], st["message"])

    db = Database()
    engine = Engine(db, cfg)

    win = MainWindow(AppContext(db, cfg, engine, log, None))
    # wire show_screen now that window exists
    win.ctx.show_screen = win.show_screen
    win.setStyleSheet(theme.stylesheet(cfg.get("accent", "red")))

    # ---- v1.3 admin-panel wiring: consent -> online license check -> heartbeat ----
    try:
        from octora.core import telemetry
        from octora.ui.telemetry_consent import maybe_ask_consent
        maybe_ask_consent(cfg, win)          # first-run only; persists the choice
        ok, msg = telemetry.validate_online(cfg)
        log.info("license server check: %s", msg)
        if telemetry.enabled(cfg):
            telemetry.send_heartbeat(db, cfg, reason="startup")
            telemetry.start_background_loop(db, cfg)
    except Exception as e:  # noqa: BLE001 — telemetry must never block startup
        log.warning("telemetry startup wiring skipped: %s", e)

    win.show()

    engine.start()

    # ---- v1.4 auto-update: non-blocking check, popup when a newer build exists
    try:
        from octora.core import updater
        from octora.core.telemetry import APP_VERSION
        updater.check_async(cfg, APP_VERSION, win)
    except Exception as e:  # noqa: BLE001 — updates must never block startup
        log.warning("update check skipped: %s", e)

    # headless smoke test hook: OCTORA_SMOKE_TEST=<seconds> auto-quits
    smoke = os.environ.get("OCTORA_SMOKE_TEST")
    if smoke:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(int(smoke) * 1000, app.quit)

    code = app.exec()
    engine.stop()
    log.info("OCTORA closed.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
