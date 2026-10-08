"""Adapter registry. Add a new protocol by writing an Adapter subclass and registering it here."""
from .base import Adapter, AdapterError  # noqa: F401

PROTOCOLS = {          # protocol key -> adapter name
    "ssh": "ssh",
    "openvpn": "openvpn",
    "vless": "xray",
    "vmess": "xray",
    "trojan": "xray",
    "zivpn": "zivpn",
    "reality": "xray",
    "hysteria2": "hysteria2",
    "wireguard": "wireguard",
}
_cache = {}


def all_adapters():
    if not _cache:
        from .ssh import SSHAdapter
        from .openvpn import OpenVPNAdapter
        from .xray import XrayAdapter
        from .zivpn import ZivpnAdapter
        from .badvpn import BadVPNAdapter
        from .hysteria import HysteriaAdapter
        from .wireguard import WireGuardAdapter
        for cls in (SSHAdapter, OpenVPNAdapter, XrayAdapter, ZivpnAdapter, HysteriaAdapter, WireGuardAdapter, BadVPNAdapter):
            _cache[cls.name] = cls()
    return _cache


def get_adapter(name):
    try:
        return all_adapters()[name]
    except KeyError:
        raise AdapterError("unknown adapter: %s" % name)


def adapter_for(protocol):
    if protocol not in PROTOCOLS:
        raise AdapterError("unknown protocol: %s" % protocol)
    return get_adapter(PROTOCOLS[protocol])
