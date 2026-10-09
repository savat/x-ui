"""Central service manager. Only allow-listed units can be controlled (never arbitrary systemctl)."""
import re

from . import config, security, shell

PROTECTED = {"unified-panel", "nginx"}     # restart only - stopping them could lock the admin out
_ACTIONS = ("start", "stop", "restart")


def known_services():
    """name -> unit. Built from the core set + every adapter's declared units."""
    from adapters import all_adapters
    names = {"unified-panel": "unified-panel.service", "nginx": "nginx.service"}
    for ad in all_adapters().values():
        for unit in ad.services:
            names[re.sub(r"\.service$", "", unit)] = unit
    return names


def unit_state(unit):
    """RUNNING | STOPPED | ERROR | NOT_INSTALLED | UNKNOWN"""
    if config.DRY_RUN:
        return "UNKNOWN"
    load = shell.run(["systemctl", "show", "-p", "LoadState", "--value", unit]).out.strip()
    if load == "not-found":
        return "NOT_INSTALLED"
    out = shell.run(["systemctl", "is-active", unit]).out.strip()
    if out in ("active", "activating", "reloading"):
        return "RUNNING"
    if out == "failed":
        return "ERROR"
    return "STOPPED"


def control_unit(action, unit):
    if action not in _ACTIONS:
        raise ValueError("invalid action")
    r = shell.run(["systemctl", action, unit], timeout=90)
    if not r.ok:
        raise RuntimeError("systemctl %s %s failed: %s" % (action, unit, r.out.strip()[-300:]))
    return unit_state(unit)


def list_services():
    out = []
    for name, unit in sorted(known_services().items()):
        out.append({"name": name, "unit": unit, "state": unit_state(unit), "protected": name in PROTECTED})
    return out


def control(action, name):
    svc = known_services()
    if name not in svc:
        raise ValueError("unknown service")
    if name in PROTECTED and action != "restart":
        raise ValueError("%s is protected: only restart is allowed from the panel" % name)
    return control_unit(action, svc[name])


def logs(name, lines=200):
    svc = known_services()
    if name not in svc:
        raise ValueError("unknown service")
    lines = max(10, min(int(lines), 1000))
    r = shell.run(["journalctl", "-u", svc[name], "-n", str(lines), "--no-pager", "-o", "short-iso"], timeout=20)
    return security.redact(r.out[-200000:])
