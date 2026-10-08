"""Parse OpenVPN status-version 1 files. Dependency-free: also imported by scripts/ovpn-auth.py."""
import glob
import os

STATUS_GLOB = "uvpn-*-status.log"


def parse_status(text):
    """Return [(common_name, real_address)] from a status-version 1 file."""
    clients, in_list = [], False
    for line in text.splitlines():
        if line.startswith("Common Name,Real Address"):
            in_list = True
            continue
        if line.startswith("ROUTING TABLE") or line.startswith("GLOBAL STATS") or line.startswith("END"):
            in_list = False
        if in_list and "," in line:
            parts = line.split(",")
            if len(parts) >= 2:
                clients.append((parts[0], parts[1]))
    return clients


def connected(varlog="/var/log"):
    res = []
    for path in glob.glob(os.path.join(varlog, "openvpn", STATUS_GLOB)):
        try:
            with open(path) as fh:
                res.extend(parse_status(fh.read()))
        except (IOError, OSError):
            continue
    return res


def count_for(username, varlog="/var/log"):
    return sum(1 for cn, _ in connected(varlog) if cn == username)
