"""Safe subprocess wrapper: never uses a shell, honours DRY_RUN, never logs stdin."""
import logging
import subprocess

from . import config

log = logging.getLogger("uvpn.shell")


class CommandError(Exception):
    pass


class Result(object):
    def __init__(self, rc, out):
        self.rc = rc
        self.out = out or ""

    @property
    def ok(self):
        return self.rc == 0


def run(cmd, timeout=60, input_text=None, check=False, env=None, cwd=None):
    if not isinstance(cmd, (list, tuple)):
        raise TypeError("cmd must be a list (no shell)")
    cmd = [str(c) for c in cmd]
    if config.DRY_RUN:
        log.info("DRY-RUN: %s", " ".join(cmd))
        return Result(0, "")
    try:
        p = subprocess.run(cmd, input=input_text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, universal_newlines=True, env=env, cwd=cwd)
        res = Result(p.returncode, p.stdout)
    except FileNotFoundError:
        res = Result(127, "command not found: %s" % cmd[0])
    except subprocess.TimeoutExpired:
        res = Result(124, "timeout after %ss: %s" % (timeout, cmd[0]))
    if check and res.rc != 0:
        raise CommandError("%s failed (rc=%s): %s" % (" ".join(cmd[:3]), res.rc, res.out.strip()[-400:]))
    return res
