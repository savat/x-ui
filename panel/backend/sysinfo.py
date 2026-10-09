"""Real (measured) system metrics read from /proc - no fake numbers."""
import os
import shutil
import threading
import time

_lock = threading.Lock()
_prev = {"t": None, "idle": 0, "total": 0}


def _cpu_times():
    with open("/proc/stat") as fh:
        parts = [int(x) for x in fh.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return idle, sum(parts)


def cpu_percent():
    with _lock:
        idle, total = _cpu_times()
        if _prev["t"] is None:
            time.sleep(0.25)
            _prev.update(t=1, idle=idle, total=total)
            idle, total = _cpu_times()
        d_total = total - _prev["total"]
        d_idle = idle - _prev["idle"]
        _prev.update(idle=idle, total=total)
        return round(100.0 * (d_total - d_idle) / d_total, 1) if d_total > 0 else 0.0


def memory():
    info = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    return {"total": total, "used": total - avail, "percent": round(100.0 * (total - avail) / total, 1) if total else 0}


def disk(path="/"):
    u = shutil.disk_usage(path)
    return {"total": u.total, "used": u.used, "percent": round(100.0 * u.used / u.total, 1)}


def uptime():
    with open("/proc/uptime") as fh:
        return int(float(fh.read().split()[0]))


def net_totals():
    rx = tx = 0
    with open("/proc/net/dev") as fh:
        for line in list(fh)[2:]:
            iface, data = line.split(":", 1)
            if iface.strip() == "lo":
                continue
            f = data.split()
            rx += int(f[0])
            tx += int(f[8])
    return {"rx_bytes": rx, "tx_bytes": tx, "note": "interface totals since boot (all users, all traffic)"}


def snapshot():
    return {"cpu_percent": cpu_percent(), "cpus": os.cpu_count(), "load": os.getloadavg(),
            "memory": memory(), "disk": disk(), "uptime": uptime(), "traffic": net_totals()}
