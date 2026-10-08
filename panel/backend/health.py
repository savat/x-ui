"""Health checks: binary / config / port / service / recent errors for every installed component."""
import re

from adapters import all_adapters
from backend import config, servicemgr, shell

# Connection-level noise every public server produces (port scanners, handshake failures, stray
# clients). These are logged at err priority but do NOT mean the service is broken. Only count
# lines that do NOT match, i.e. real service failures (config/startup crashes, bind errors, panics).
_BENIGN = re.compile(
    r"failed to (?:read|write)|try another one|no suitable inbound|handshake|reject|"
    r"connection from|(?:read|write) tcp|i/o timeout|broken pipe|connection (?:reset|refused)|"
    r"mux client connection|websocket|socks", re.I)


def _core():
    res = [("panel service active", servicemgr.unit_state("unified-panel.service") in ("RUNNING", "UNKNOWN"), ""),
           ("nginx service active", servicemgr.unit_state("nginx.service") in ("RUNNING", "UNKNOWN"), "")]
    t = shell.run(["nginx", "-t"])
    res.append(("nginx config valid", t.ok, t.out.strip()[-200:] if not t.ok else ""))
    return res


def _recent_errors(units):
    n = 0
    for u in units:
        r = shell.run(["journalctl", "-u", u, "-p", "err", "--since", "10 min ago", "--no-pager", "-q"])
        n += len([l for l in r.out.splitlines() if l.strip() and not _BENIGN.search(l)])
    return n


def run_all():
    """Returns [{"component", "ok", "checks": [{"name","ok","msg"}]}]"""
    report = [{"component": "Panel/Nginx", "checks": _core()}]
    for ad in all_adapters().values():
        if not ad.installed():
            continue
        checks = list(ad.health())
        errs = _recent_errors(ad.services) if not config.DRY_RUN else 0
        checks.append(("no critical log errors (10 min)", errs == 0, "%d error lines" % errs if errs else ""))
        report.append({"component": ad.label, "checks": checks})
    for item in report:
        item["checks"] = [{"name": n, "ok": bool(ok), "msg": m} for n, ok, m in item["checks"]]
        item["ok"] = all(c["ok"] for c in item["checks"])
    return report
