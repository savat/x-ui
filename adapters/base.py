"""Adapter interface. The panel only talks to adapters; it never knows protocol internals.

Interface (plan section 19):
    install / uninstall / configure / start / stop / restart / status /
    create_user / delete_user / list_users
Extra hooks used by the user manager:
    revoke_user  - cut access but keep the account (expiry / disable)
    sync         - declarative adapters (ZIVPN) re-render config from the DB here
    share        - links / files a client needs
    health       - checks used by health-check
    online       - {username: connection_count}
"""
import json
import os
import re
import shutil
import tempfile

from backend import config, servicemgr, shell


class AdapterError(Exception):
    pass


def write_file(path, content, mode=0o644, group=None):
    """Atomic write (tmp + rename). Returns True when content changed."""
    try:
        with open(path, "r") as fh:
            if fh.read() == content:
                os.chmod(path, mode)
                return False
    except (IOError, OSError):
        pass
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".uvpn-")
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    os.chmod(tmp, mode)
    if group and not config.DRY_RUN:
        try:
            shutil.chown(tmp, user="root", group=group)
        except (LookupError, OSError):
            pass
    os.replace(tmp, path)
    return True


def listening(proto, port):
    """True when something listens on proto ('tcp'|'udp') port."""
    if config.DRY_RUN:
        return True
    r = shell.run(["ss", "-lnH", "-t" if proto == "tcp" else "-u"])
    return re.search(r"[:.]%d\s" % int(port), r.out) is not None


def port_free(proto, port):
    """Pre-install check. Never kills the owner - the caller just refuses to continue."""
    if config.DRY_RUN:
        return True
    return not listening(proto, port)


def apt_install(*pkgs):
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    shell.run(["apt-get", "install", "-y", "--no-install-recommends"] + list(pkgs), timeout=900, check=True, env=env)


class Adapter(object):
    name = ""
    label = ""
    protocols = ()
    declarative = False

    @property
    def services(self):
        return ()

    # ---- install state --------------------------------------------------
    def _marker(self):
        return os.path.join(config.CONF_DIR, "installed", self.name)

    def installed(self):
        return os.path.exists(self._marker())

    def mark_installed(self, info=None):
        write_file(self._marker(), json.dumps(info or {}), 0o600)

    def unmark_installed(self):
        try:
            os.remove(self._marker())
        except OSError:
            pass

    # ---- lifecycle ------------------------------------------------------
    def install(self, opts=None):
        raise NotImplementedError

    def uninstall(self):
        raise NotImplementedError

    def configure(self):
        pass

    def start(self):
        for u in self.services:
            servicemgr.control_unit("start", u)

    def stop(self):
        for u in self.services:
            servicemgr.control_unit("stop", u)

    def restart(self):
        for u in self.services:
            servicemgr.control_unit("restart", u)

    def status(self):
        return dict((u, servicemgr.unit_state(u)) for u in self.services)

    def overall_status(self):
        if not self.installed():
            return "NOT_INSTALLED"
        states = list(self.status().values())
        if any(s == "ERROR" for s in states):
            return "ERROR"
        if states and all(s in ("RUNNING", "UNKNOWN") for s in states):
            return "RUNNING"
        return "STOPPED"

    # ---- users ----------------------------------------------------------
    def create_user(self, user, account):
        """Idempotent: create or (re)enable the account and apply expiry. Returns config dict to merge."""
        return {}

    def delete_user(self, user, account):
        pass

    def revoke_user(self, user, account):
        self.delete_user(user, account)

    def list_users(self):
        return []

    def sync(self):
        pass

    def online(self):
        return {}

    def share(self, user, account, hostinfo):
        return {"links": [], "files": [], "info": {}}

    def info(self):
        return {}

    def health(self):
        return []
