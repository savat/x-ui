"""Central paths/config. Every path can be overridden by env (used for tests / dry-run)."""
import os

HOME = os.environ.get("UVPN_HOME", "/opt/unified-vpn")
DATA = os.environ.get("UVPN_DATA", "/var/lib/unified-vpn")
CONF_DIR = os.environ.get("UVPN_CONF", os.path.join(HOME, "config"))
DB_PATH = os.environ.get("UVPN_DB", os.path.join(DATA, "database.db"))
BACKUP_DIR = os.environ.get("UVPN_BACKUPS", os.path.join(HOME, "backups"))
SCRIPTS_DIR = os.environ.get("UVPN_SCRIPTS", os.path.join(HOME, "scripts"))
ETC = os.environ.get("UVPN_ETC", "/etc")
VARLOG = os.environ.get("UVPN_VARLOG", "/var/log")
SYSTEMD_DIR = os.environ.get("UVPN_SYSTEMD_DIR", os.path.join(ETC, "systemd/system"))
NGINX_HTTPS_D = os.environ.get("UVPN_NGINX_D", os.path.join(ETC, "unified-vpn/nginx.d"))
NGINX_HTTP_D = os.environ.get("UVPN_NGINX_HTTP_D", os.path.join(ETC, "unified-vpn/nginx-http.d"))
PY = os.environ.get("UVPN_PYTHON", os.path.join(HOME, "venv/bin/python"))

# DRY_RUN=1: external commands are logged, not executed (development / CI only)
DRY_RUN = os.environ.get("UVPN_DRY_RUN") == "1"


def load_env_file(path=None):
    """Load KEY=VALUE lines (panel.env) into os.environ without overriding existing values."""
    path = path or os.path.join(CONF_DIR, "panel.env")
    try:
        with open(path, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except (IOError, OSError):
        pass


load_env_file()
