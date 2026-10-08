"""Health checks for every installed component.

run_all() first calls sync() on each installed adapter so declarative components render their
config from the live DB and reconcile stale runtime state (e.g. a Hysteria unit that older code
left crash-looping on an empty userpass). Then it collects per-adapter checks. We deliberately do
not grep application logs for errors - every public service logs constant connection-level noise
(port scanners, dropped handshakes) that has nothing to do with health; the authoritative signals
are binary/config validity, `systemctl is-active`, restart-loop counters and bound ports.
"""
from adapters import all_adapters
from backend import config, servicemgr, shell


def _core():
    res = [("panel service active", servicemgr.unit_state("unified-panel.service") in ("RUNNING", "UNKNOWN"), ""),
           ("nginx service active", servicemgr.unit_state("nginx.service") in ("RUNNING", "UNKNOWN"), "")]
    t = shell.run(["nginx", "-t"])
    res.append(("nginx config valid", t.ok, t.out.strip()[-200:] if not t.ok else ""))
    return res


def run_all():
    """Returns [{"component", "ok", "checks": [{"name","ok","msg"}]}]"""
    report = [{"component": "Panel/Nginx", "checks": _core()}]
    for ad in all_adapters().values():
        if not ad.installed():
            continue
        try:
            ad.sync()
        except Exception as exc:                     # reconcile must never take health down
            report.append({"component": ad.label,
                           "checks": [{"name": "reconcile", "ok": False, "msg": str(exc)[-200:]}]})
            continue
        checks = list(ad.health())
        report.append({"component": ad.label, "checks": checks})
    for item in report:
        item["checks"] = [{"name": n, "ok": bool(ok), "msg": m} for n, ok, m in item["checks"]]
    for item in report:
        item["ok"] = all(c["ok"] for c in item["checks"]) or not item["checks"]
    return report