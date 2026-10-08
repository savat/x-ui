#!/usr/bin/env python3
"""Minimal HTTP-Upgrade (WebSocket-style) -> raw TCP tunnel for SSH / OpenVPN-TCP.

Behaviour matches common SSH-WS clients: after the client's HTTP request containing
'Upgrade: websocket' we answer '101 Switching Protocols' and then pipe raw bytes.
Binds to 127.0.0.1 only; nginx terminates TLS and exposes it on a path.
"""
import argparse
import asyncio
import logging

log = logging.getLogger("ws_tunnel")
RESP = (b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(creader, cwriter, target):
    try:
        head = await asyncio.wait_for(creader.readuntil(b"\r\n\r\n"), timeout=10)
    except Exception:
        cwriter.close()
        return
    if b"upgrade: websocket" not in head.lower():
        cwriter.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        await cwriter.drain()
        cwriter.close()
        return
    try:
        treader, twriter = await asyncio.wait_for(asyncio.open_connection(*target), timeout=5)
    except Exception as exc:
        log.warning("target connect failed: %s", exc)
        cwriter.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        cwriter.close()
        return
    cwriter.write(RESP)
    await cwriter.drain()
    await asyncio.gather(pipe(creader, twriter), pipe(treader, cwriter))


async def main(args):
    host, port = args.listen.rsplit(":", 1)
    thost, tport = args.target.rsplit(":", 1)
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("refusing to bind a non-loopback address")
    server = await asyncio.start_server(lambda r, w: handle(r, w, (thost, int(tport))), host, int(port), limit=2 ** 16)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="127.0.0.1:10015")
    ap.add_argument("--target", default="127.0.0.1:22")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(main(ap.parse_args()))
