"""Thin wrapper around scripts/backup.sh (encrypted archives, never plain private keys)."""
import os
import re
import subprocess

from . import config, shell

NAME_RE = re.compile(r"^uvpn-\d{8}-\d{6}\.tar\.gz\.enc$")


def _script():
    return os.path.join(config.SCRIPTS_DIR, "backup.sh")


def list_backups():
    try:
        names = sorted((n for n in os.listdir(config.BACKUP_DIR) if NAME_RE.match(n)), reverse=True)
    except OSError:
        return []
    return [{"name": n, "size": os.path.getsize(os.path.join(config.BACKUP_DIR, n)),
             "mtime": int(os.path.getmtime(os.path.join(config.BACKUP_DIR, n)))} for n in names]


def create():
    r = shell.run(["bash", _script(), "create"], timeout=600)
    if not r.ok:
        raise RuntimeError("backup failed: %s" % r.out.strip()[-300:])
    return r.out.strip().splitlines()[-1] if r.out.strip() else ""


def path_of(name):
    if not NAME_RE.match(name):
        raise ValueError("invalid backup name")
    p = os.path.join(config.BACKUP_DIR, name)
    if not os.path.isfile(p):
        raise KeyError("backup not found")
    return p


def delete(name):
    os.remove(path_of(name))


def restore(name):
    """Runs detached: the restore restarts the panel itself."""
    p = path_of(name)
    if config.DRY_RUN:
        return
    subprocess.Popen(["bash", _script(), "restore", p], start_new_session=True,
                     stdout=open(os.path.join(config.DATA, "restore.log"), "a"), stderr=subprocess.STDOUT)
