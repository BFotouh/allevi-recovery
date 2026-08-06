#!/usr/bin/env python3
"""
Allevi Client Shim  --  stands in for the discontinued "Allevi Client" desktop app
--------------------------------------------------------------------------------
Run:   python3 allevi_client_shim.py
Then:  reload https://bioprint.allevi3d.com  -- your printer should flip from
       DISCONNECTED to connected.

WHY THIS EXISTS
    Allevi's web app (bioprint.allevi3d.com) polls http://127.0.0.1:8000 looking
    for their "Allevi Client" desktop application -- that's what "Adapter Mode"
    actually installs. You can see it in the browser console as a repeating

        GET http://127.0.0.1:8000/state         net::ERR_CONNECTION_REFUSED
        GET http://127.0.0.1:8000/client-state  net::ERR_CONNECTION_REFUSED

    CONNECTION_REFUSED (rather than a blocked-mixed-content error) means the
    browser is willing to make that call -- there's simply nothing listening.
    This script listens, speaks the same five endpoints, and forwards them to
    the printer over the local link. Allevi's own Client download and the
    TP-Link USB adapter are not needed.

    The cloud REST API, the slicer, and your file library are all still online.
    The only thing that died is the printer's telemetry uplink -- which is
    exactly the piece this shim replaces locally.

RELATIONSHIP TO allevi_control.py
    Completely independent. Different file, different port:
        allevi_control.py     -> 127.0.0.1:8765   (your own control panel)
        allevi_client_shim.py -> 127.0.0.1:8000   (this, for Allevi's web app)
    They do not import each other and do not share state. Run either one alone,
    or both at the same time. Nothing here modifies the existing panel.

SECURITY
    - Binds to 127.0.0.1 only, so nothing on your network can reach it.
    - CORS is restricted to ALLOWED_ORIGINS below (Allevi's app). Other pages in
      your browser get no CORS headers and are therefore blocked by the browser.
      That matters, because this endpoint can move the printer.
"""

import http.server
import socketserver
import subprocess
import json
import tempfile
import os
import re

# ── Config ────────────────────────────────────────────────────────────
# You should not need to edit any of this -- the printer is auto-discovered at
# startup (see find_printer below), which is what makes this script portable to
# any machine without hand-editing an interface name.
#
# Optional manual override, if discovery ever fails:
#     PRINTER_OVERRIDE = "fe80::5c11:5cab:dab9:7ba7%25en7"   (%25 = encoded %)
PRINTER_OVERRIDE = os.environ.get("ALLEVI_PRINTER")  # e.g. "fe80::...%25en5"

# Last known printer address. Used only as a fast-path hint during discovery --
# the link-local address belongs to the PRINTER, so it stays the same across
# machines; only the interface name (%enN) is machine-specific.
KNOWN_PRINTER_ADDR = "fe80::5c11:5cab:dab9:7ba7"

# Raspberry Pi Foundation MAC prefix. The Allevi 3's controller is a Pi, so this
# is a strong hint when scanning the IPv6 neighbor table.
RPI_OUI = "b8:27:eb"

PRINTER_PORT = 8000

# The port Allevi's web app expects the Client to be on. Do not change unless
# you also change what the web app polls (you can't -- it's hardcoded in their
# bundle as http://127.0.0.1:8000).
LOCAL_PORT = 8000

# Only these page origins get CORS headers. Anything else is refused by the
# browser, so a random tab can't drive your printer.
ALLOWED_ORIGINS = {
    "https://bioprint.allevi3d.com",
    "http://bioprint.allevi3d.com",
}

CURL_TIMEOUT = 20
CLIENT_VERSION = "1.0.0-local-shim"
# ─────────────────────────────────────────────────────────────────────


def _probe(addr, iface, timeout=3):
    """Return the printer's serial number if an Allevi printer answers at
    [addr%iface]:8000, else None."""
    url = f"https://[{addr}%25{iface}]:{PRINTER_PORT}/state"
    try:
        r = subprocess.run(["curl", "-gk", "-s", "-m", str(timeout), url],
                           capture_output=True, timeout=timeout + 3)
        return json.loads(r.stdout.decode("utf-8", "replace"))["state"]["serialNumber"]
    except Exception:
        return None


def _interfaces():
    """Physical-ish interfaces worth scanning, newest first (USB-Ethernet
    adapters tend to get the highest number, and that's usually the printer)."""
    try:
        out = subprocess.run(["ifconfig", "-l"], capture_output=True,
                             timeout=5).stdout.decode()
    except Exception:
        return []
    skip = ("lo", "gif", "stf", "awdl", "llw", "utun", "bridge", "ap", "anpi")
    names = [i for i in out.split() if not i.startswith(skip)]
    return sorted(names, reverse=True)


def _neighbors():
    """(addr, iface) pairs from the IPv6 neighbor table, Raspberry Pi MACs first."""
    try:
        out = subprocess.run(["ndp", "-an"], capture_output=True,
                             timeout=8).stdout.decode("utf-8", "replace")
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith("fe80::"):
            continue
        if "%" not in parts[0]:
            continue
        addr, iface = parts[0].split("%", 1)
        found.append((addr, iface, parts[1].lower().startswith(RPI_OUI)))
    # Raspberry Pi MACs first -- most likely to be the printer
    found.sort(key=lambda t: not t[2])
    return [(a, i) for a, i, _ in found]


def find_printer(verbose=True):
    """Locate the printer and return its base URL, or None.

    Strategy, cheapest first:
      1. explicit override
      2. last-known address, tried against each local interface
      3. full scan: multicast-ping each interface, then probe the neighbor table
    """
    def say(m):
        if verbose:
            print(m, flush=True)

    if PRINTER_OVERRIDE:
        say(f"  using ALLEVI_PRINTER override: {PRINTER_OVERRIDE}")
        return f"https://[{PRINTER_OVERRIDE}]:{PRINTER_PORT}"

    ifaces = _interfaces()

    # 2. fast path -- the printer's address is stable; only the interface varies
    for iface in ifaces:
        sn = _probe(KNOWN_PRINTER_ADDR, iface, timeout=2)
        if sn:
            say(f"  found printer {sn} at {KNOWN_PRINTER_ADDR}%{iface}")
            return f"https://[{KNOWN_PRINTER_ADDR}%25{iface}]:{PRINTER_PORT}"

    # 3. full scan -- handles a printer whose address has changed
    say("  last-known address did not answer; scanning for the printer...")
    for iface in ifaces:
        subprocess.run(["ping6", "-c", "2", "-I", iface, "ff02::1"],
                       capture_output=True, timeout=15)
    seen = set()
    for addr, iface in _neighbors():
        if (addr, iface) in seen:
            continue
        seen.add((addr, iface))
        sn = _probe(addr, iface)
        if sn:
            say(f"  found printer {sn} at {addr}%{iface}")
            return f"https://[{addr}%25{iface}]:{PRINTER_PORT}"

    say("  no Allevi printer found on any interface")
    return None


# Resolved lazily so the shim can start before the printer is plugged in, and
# recover on its own if the cable is moved or the address changes.
_printer_base = None


def get_printer_base(rediscover=False):
    global _printer_base
    if _printer_base is None or rediscover:
        found = find_printer(verbose=True)
        if found:
            _printer_base = found
    return _printer_base


def curl(args, timeout=CURL_TIMEOUT, binary=False):
    """Talk to the printer. curl handles the self-signed cert (-k) and the
    IPv6 link-local zone id, which Python's http.client does not do cleanly."""
    try:
        result = subprocess.run(
            ["curl", "-sk", "-m", str(timeout)] + args,
            capture_output=True, timeout=timeout + 5
        )
        out = result.stdout
        if binary:
            return out
        return out.decode("utf-8", "replace") or '{"status":false,"error":"empty response from printer"}'
    except subprocess.TimeoutExpired:
        return b'' if binary else '{"status":false,"error":"timeout talking to printer"}'
    except Exception as e:
        return b'' if binary else json.dumps({"status": False, "error": str(e)})


def proxy(args, timeout=CURL_TIMEOUT):
    """Forward a call to the printer. '{base}' in args is replaced with the
    discovered base URL. If the printer doesn't answer, re-run discovery once
    and retry -- that way moving the cable to another port, or the printer
    coming up with a new address, heals itself without a restart."""
    base = get_printer_base()
    if not base:
        return '{"status":false,"error":"no Allevi printer found on any interface"}'

    out = curl([a.replace("{base}", base) for a in args], timeout=timeout)
    if "empty response" in out or "timeout talking" in out:
        base = get_printer_base(rediscover=True)
        if not base:
            return '{"status":false,"error":"no Allevi printer found on any interface"}'
        out = curl([a.replace("{base}", base) for a in args], timeout=timeout)
    return out


def proxy_get(path, timeout=CURL_TIMEOUT):
    return proxy(["{base}" + path], timeout=timeout)


def parse_multipart(body: bytes, content_type: str):
    """Minimal multipart/form-data parser.

    Deliberately tolerant: Allevi's client code sets a bogus
    `Content-Type: mime/multipart` header, so the boundary may be missing from
    the header and has to be recovered from the body itself.
    """
    boundary = None
    m = re.search(r'boundary=("?)([^";]+)\1', content_type or "", re.I)
    if m:
        boundary = m.group(2).encode()
    if not boundary:
        first = body.split(b"\r\n", 1)[0]
        if first.startswith(b"--"):
            boundary = first[2:]
    if not boundary:
        return {}

    fields = {}
    for part in body.split(b"--" + boundary):
        part = part.lstrip(b"\r\n")
        if not part or part.startswith(b"--"):
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        head_s = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]*)"', head_s)
        filename = re.search(r'filename="([^"]*)"', head_s)
        if name:
            fields[name.group(1)] = {
                "data": data,
                "filename": filename.group(1) if filename else None,
            }
    return fields


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "AlleviClientShim"

    # ---- plumbing -----------------------------------------------------
    def _cors(self):
        origin = self.headers.get("Origin")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Credentials", "true")
            # Chrome's Private Network Access check: an https page reaching a
            # loopback address sends Access-Control-Request-Private-Network on
            # the preflight and requires this header back.
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        req_headers = self.headers.get("Access-Control-Request-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Headers", req_headers)
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    # ---- endpoints the Allevi web app calls ---------------------------
    def do_GET(self):
        if self.path.startswith("/state"):
            # Straight passthrough of the printer's live telemetry.
            self._send(200, proxy_get("/state"))

        elif self.path.startswith("/client-state"):
            # The real Client reported on ITSELF here (which network interface
            # it found the printer on, its version). The printer has no such
            # endpoint, so we synthesize the shape the app's AlleviClientState
            # interface expects. status:true is what marks the client "up".
            self._send(200, json.dumps({
                "networkInterfaces": ["en7"],
                "printerNetworkInterface": 0,
                "clientVersion": CLIENT_VERSION,
                "status": True,
            }))

        else:
            self._send(404, '{"status":false,"error":"not found"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "")

        if self.path.startswith("/commands"):
            fields = parse_multipart(raw, ctype)
            cmds = ""
            if "commands" in fields:
                cmds = fields["commands"]["data"].decode("utf-8", "replace")
            if not cmds:
                self._send(400, '{"status":false,"error":"no commands field in request"}')
                return
            print(f"  -> commands: {cmds[:160]}", flush=True)
            self._send(200, proxy(["-X", "POST", "{base}/commands", "-F", f"commands={cmds}"]))

        elif self.path.startswith("/file"):
            fields = parse_multipart(raw, ctype)
            if "file" not in fields:
                self._send(400, '{"status":false,"error":"no file field in request"}')
                return
            blob = fields["file"]["data"]
            name = fields["file"]["filename"] or "PrintFile.gcode"
            print(f"  -> file upload: {name} ({len(blob)} bytes)", flush=True)
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", suffix="_" + os.path.basename(name), delete=False
                ) as f:
                    f.write(blob)
                    tmp_path = f.name
                out = proxy(["-X", "POST", "{base}/file",
                             "-F", f"file=@{tmp_path};filename={os.path.basename(name)}"],
                            timeout=120)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            self._send(200, out)

        elif self.path.startswith("/logs/read"):
            self._send(200, proxy([
                "-X", "POST", "{base}/logs/read",
                "-H", "Content-Type: application/json",
                "-d", raw.decode("utf-8", "replace") or '{"count":200}',
            ]), ctype="text/plain")

        else:
            self._send(404, '{"status":false,"error":"not found"}')

    def log_message(self, fmt, *args):
        # One concise line per request instead of the noisy default.
        print(f"  {self.command} {self.path}", flush=True)


class Server(socketserver.ThreadingTCPServer):
    # Threaded: the app polls /state every 6s while also issuing commands, and
    # a single-threaded server would serialize those behind each other.
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print("Allevi Client Shim", flush=True)
    print(f"  listening on : http://127.0.0.1:{LOCAL_PORT}  (localhost only)", flush=True)
    print("  locating printer...", flush=True)
    base = get_printer_base()
    if base:
        print(f"  forwarding to: {base}", flush=True)
    else:
        print("  no printer found yet -- check the Ethernet cable.", flush=True)
        print("  Starting anyway; it will keep looking on each request.", flush=True)
    print(f"  CORS allowed : {', '.join(sorted(ALLOWED_ORIGINS))}", flush=True)
    print("", flush=True)
    print("  Independent of allevi_control.py (port 8765) -- both can run at once.", flush=True)
    print("  Reload bioprint.allevi3d.com once this is up. Ctrl+C to stop.", flush=True)
    print("", flush=True)
    try:
        with Server(("127.0.0.1", LOCAL_PORT), Handler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        print(f"\nCould not start on port {LOCAL_PORT}: {e}", flush=True)
        print("Something else is already using port 8000 -- if it's an older copy", flush=True)
        print("of this shim, stop it first:  pkill -f allevi_client_shim.py", flush=True)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
