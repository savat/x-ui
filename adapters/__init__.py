"""Adapter registry. ZIVPN is the only protocol this panel manages."""
from .base import Adapter, AdapterError  # noqa: F401

PROTOCOLS = {"zivpn": "zivpn"}      # protocol key -> adapter name
_cache = {}


def all_adapters():
    if not _cache:
        from .zivpn import ZivpnAdapter
        _cache[ZivpnAdapter.name] = ZivpnAdapter()
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
