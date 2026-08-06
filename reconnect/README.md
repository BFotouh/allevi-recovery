# Allevi Reconnect

Reconnects your Allevi 3 bioprinter to the Allevi website
(`bioprint.allevi3d.com`) so it shows as connected instead of
**DISCONNECTED** — without any special adapter and without downloading
anything from Allevi.

## The problem

Allevi's printers were discontinued, and the piece that lets your printer
report its status to their website — "Cloud Mode" — depends on Allevi's own
backend infrastructure. That's the part that's no longer reliable: the
website itself, your login, your saved files, and the slicer all still work
fine, but the printer can't reach them the way it used to, so the website
just shows it as offline.

Allevi's own documentation describes a workaround for this called **Adapter
Mode**. In practice it's awkward:

- It requires a specific **TP-Link USB Wi-Fi adapter** — a piece of hardware
  most people don't have and would need to track down and buy.
- It requires installing Allevi's own **"Allevi Client"** desktop program,
  which is no longer being distributed anywhere obvious.
- The setup instructions are written around Windows-style Wi-Fi adapter
  selection and don't translate cleanly to a Mac.
- Even when it works, it means giving up your normal Wi-Fi connection while
  a second adapter talks to the printer — inconvenient for something you
  might want to do regularly.

## What this tool does

The Allevi website is actually already looking for something on your own
computer — it repeatedly tries to reach `http://127.0.0.1:8000`, hoping to
find the Allevi Client program running there. Normally nothing answers, so
it gives up and shows the printer as disconnected.

This tool answers instead. It runs quietly on your computer, finds your
printer automatically over a normal Ethernet cable, and relays messages
between the website and the printer — standing in for the Allevi Client
software without you needing to install it, and without the special Wi-Fi
adapter.

Nothing is installed system-wide. It only runs while you have it open, it
only accepts connections from your own computer, and it only talks to
Allevi's own website — no other webpage can use it.

## What you need

- A Mac, Windows PC, or Linux computer
- An Ethernet cable from the printer to your computer (most laptops need a
  USB‑C → Ethernet adapter)
- Your own Allevi account login
- About 5 minutes

**Only one computer can be connected at a time** over a direct cable, since
the printer has one Ethernet port. If more than one person needs access,
connect the printer and every computer to the same network switch instead.

## Setup

### On a Mac — the easy way

1. Download this whole `reconnect` folder.
2. Plug in the Ethernet cable and turn the printer on. Give it about a
   minute to finish starting up.
3. Double-click **`Start Allevi Reconnect.command`**.

A Terminal window opens and does the rest. Once you see a line saying it
found your printer, go to `bioprint.allevi3d.com` and refresh the page —
your printer should now show as connected.

Leave that Terminal window open for as long as you're using the printer.
Closing it disconnects things again; just double-click the file again next
time.

If double-clicking doesn't work (some Macs open `.command` files in a text
editor by default instead of running them), right-click it, choose **Open**,
and confirm — or follow the manual steps below instead.

### Manual setup (Mac, Windows, or Linux)

If you'd rather run it yourself, or you're on Windows or Linux:

**1. Check whether you have Python.**

- **Mac / Linux** — open Terminal and run `python3 --version`
- **Windows** — open Command Prompt and run `python --version`

Any version 3.7 or newer works. If it's missing, install it from
[python.org/downloads](https://www.python.org/downloads/).

> **Windows only:** on the installer's first screen, tick **"Add python.exe
> to PATH"**. This is the single most common thing people miss, and without
> it the `python` command won't be found afterwards.

You do not need to install anything else — no extra packages.

**2. Connect the printer.** Plug in the Ethernet cable, power the printer on,
and give it about a minute.

**3. Run it.**

- **Mac / Linux** — in Terminal, type `python3 ` (with a trailing space),
  drag `allevi_client_shim.py` into the window, and press Return.
- **Windows** — in Command Prompt, type `python ` (with a trailing space),
  drag `allevi_client_shim.py` into the window, and press Enter.

You should see it report finding your printer by name. Leave that window
open, then reload `bioprint.allevi3d.com`.

Your computer may ask for a network permission the first time (macOS: "find
devices on your local network"; Windows: a firewall prompt) — allow it, or
the printer won't be found.

## How to tell it's working

Open a second Terminal/Command Prompt window and run:

```
curl -s -H "Origin: https://bioprint.allevi3d.com" http://127.0.0.1:8000/state
```

(On Windows, use `curl.exe` instead of `curl`.)

If it's working, you'll get back a block of text with live printer
information. Then check the website itself — your printer should show as
connected after a refresh.

## Troubleshooting

**Run the built-in diagnostic.** Start it the same way as above but add
`--diagnose` at the end. It reports exactly what it can and can't find on
your network, which is the fastest way to tell what's wrong if the printer
isn't being found.

**"Address already in use."** Something is already using port 8000 — often
just another copy of this tool already running (check whether the website
already shows connected before restarting anything).

**Printer not found.** Double-check the Ethernet cable at both ends, make
sure the printer finished booting, and confirm you allowed the network
permission prompt. On Windows, also check that your Ethernet adapter has a
proper driver installed (Device Manager) and that IPv6 is enabled on it.

**Website still shows disconnected.** Make sure the tool's window is still
open and hasn't shown an error, then do a hard refresh of the page
(Shift+Cmd+R on Mac, Ctrl+F5 on Windows).

## A note on safety

This connection can move the printer — it's a real, working link to the
hardware, not a simulation. Watch the printer while you're using it, and
remember that unplugging it from the wall is the only guaranteed way to stop
it immediately; software controls always have to travel over the network
first.

## Disclaimer

This is an independent, community-made tool. It is not made, distributed, or
supported by Allevi, CELLINK, BICO, or any other manufacturer.

## License

Licensed under AGPL-3.0 — see the `LICENSE` file in the root of this
repository. In short: you're free to use and modify this, but if you modify
it and let others use your version — including running it as a hosted
service — your version has to stay open source too.
