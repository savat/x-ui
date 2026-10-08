"""Health checks: binary / config / port / service / recent errors for every installed component."""
import re

from adapters import all_adapters
from backend import config, servicemgr, shell

# Only these systemd messages prove a service actually broke (crash loop, exit-code failure).
# Grepping app logs for `err`-priority lines is useless: public servers get constant connection
# noise (port scanners, dropped/rejected handshakes) that is logged at err but means nothing.
_UNIT_FAILURE = re.compile(
    r"Main process exited|Failed with result|Result: exit-code|start request repeated too quickly|"
    r"Failed to start|Job for .* failed")


def _core():
    res = [("panel service active", servicemgr.unit_state("unified-panel.service") in ("RUNNING", "UNKNOWN"), ""),
           ("nginx service active", servicemgr.unit_state("nginx.service") in ("RUNNING", "UNKNOWN"), "")]
    t = shell.run(["nginx", "-t"])
    res.append(("nginx config valid", t.ok, t.out.strip()[-200:] if not t.ok else ""))
    return res


def _recent_errors(units):
    n = 0
    for u in units:
        r = shell.run(["journalctl", "-u", u, "--since", "2 min ago", "--no-pager", "-q"])
        n += len([l for l in r.out.splitlines() if _UNIT_FAILURE.search(l)])
    return n


def run_all():
    """Returns [{"component", "ok", "checks": [{"name","ok","msg"}]}]"""
    report = [{"component": "Panel/Nginx", "checks": _core()}]
    for ad in all_adapters().values():
        if not ad.installed():
            continue
        checks = list(ad.health())
        errs = _recent_errors(ad.services) if not config.DRY_RUN else 0
        checks.append(("no service crashes (recent)", errs == 0, "%d failure lines" % errs if errs else ""))
        report.append({"component": ad.label, "checks": checks})
    for item in report:
        item["checks"] = [{"name": n, "ok": bool(ok), "msg": m} for n, ok, m in item["checks"]]
        item["ok"] = all(c["ok"] for c in item["checks"])
    return report
