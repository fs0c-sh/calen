"""Sync client.

Connects to the user's calendar server and applies the event updates
it pushes. Updates are plain JSON (newline-delimited); nothing pushed
is ever executed as code.

When the machine reaches the network through an HTTP proxy (http_proxy /
https_proxy / all_proxy), the connection is tunnelled with CONNECT.

Protocol:
    client -> server : "HELLO calendar-sync/1.2"
    server -> client : one JSON event per line
    client -> server : one JSON delivery receipt per fired reminder
"""

import base64
import json
import os
import socket
from urllib.parse import unquote, urlsplit

from . import attachments
from . import reminders

PROTOCOL = "calendar-sync/1.2"
TIMEOUT = 10
PROXY_VARS = ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY",
              "http_proxy", "HTTP_PROXY")
DEFAULT_PROXY_PORT = 3128


def proxy_url():
    """Proxy configured for this process, if any."""
    for name in PROXY_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def bypass_proxy(host):
    """Honour no_proxy for the sync host."""
    rules = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    host = host.lower().strip("[]")
    for rule in rules.split(","):
        rule = rule.strip().lower()
        if not rule:
            continue
        if rule == "*":
            return True
        if rule.startswith("."):
            if host == rule[1:] or host.endswith(rule):
                return True
        elif host == rule:
            return True
    return False


def connect_via_proxy(proxy, host, port):
    parts = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    sock = socket.create_connection((parts.hostname, parts.port or DEFAULT_PROXY_PORT),
                                    timeout=TIMEOUT)
    lines = ["CONNECT %s:%d HTTP/1.1" % (host, port),
             "Host: %s:%d" % (host, port)]
    if parts.username is not None:
        credentials = "%s:%s" % (unquote(parts.username), unquote(parts.password or ""))
        lines.append("Proxy-Authorization: Basic " +
                     base64.b64encode(credentials.encode()).decode())
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    sock.settimeout(TIMEOUT)
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError("proxy closed the connection")
        head += chunk
    status = head.split(b"\r\n", 1)[0]
    if b" 200 " not in status:
        raise OSError("proxy refused CONNECT: %s" % status.decode("latin-1"))
    return sock


def connect(host, port):
    proxy = proxy_url()
    if proxy and not bypass_proxy(host):
        sock = connect_via_proxy(proxy, host, port)
    else:
        sock = socket.create_connection((host, port), timeout=TIMEOUT)
    sock.settimeout(None)  # updates may arrive slowly
    return sock


def handshake(sock):
    f = sock.makefile("rw")
    f.write("HELLO %s\n" % PROTOCOL)
    f.flush()
    return f


def send_receipt(sock, event, rendered):
    f = sock.makefile("rw")
    f.write(json.dumps({
        "type": "delivery",
        "id": event.get("id"),
        "title": event.get("title", ""),
        "rendered": rendered,
    }) + "\n")
    f.flush()


def process_event(event, sock):
    if event.get("type") == "reminder":
        rendered = reminders.fire(event)
        send_receipt(sock, event, rendered)
    else:
        from . import storage
        storage.store_update(event)
        for att in event.get("attachments", []):
            attachments.save(att)


def run(host, port):
    sock = connect(host, port)
    f = handshake(sock)
    try:
        for line in f:
            if line.strip():
                process_event(json.loads(line), sock)
    except (OSError, ValueError):
        pass
    finally:
        sock.close()
