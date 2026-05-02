# Always-on remote diagnostic node — Raspberry Pi

The tool runs fine from a laptop for one-off site visits, but if you want **continuous remote visibility** of a customer's rack, a Raspberry Pi makes a tidy always-on node:

- Pi sits next to the rack, USB-RS232 cable permanently connected to the master pack's console port.
- Flask app runs as a systemd service so it auto-starts on boot.
- Tailscale (or any VPN / reverse tunnel of your choice) makes `http://battery-pi:8080` reachable from your office without exposing it to the public internet.

Tested on a Raspberry Pi 4 / Pi 5 running **Raspberry Pi OS Lite 64-bit (Trixie / Debian 13)**. Should work unchanged on any Debian-based Pi image with Python 3.10+.

---

## 1. Flash and first boot

Use Raspberry Pi Imager and pick **Raspberry Pi OS Lite (64-bit)**. In the Imager's "Edit settings" panel, set:

- Hostname (e.g. `battery-pi`)
- Username + password (or paste an SSH public key)
- Wi-Fi credentials (skip if Ethernet)
- Locale / timezone

Eject the SD card, slot it into the Pi, and power on. First boot takes ~60 seconds. Confirm the Pi is up:

```bash
ssh <user>@<hostname>.local
# or use the IP if mDNS doesn't work on your network
```

---

## 2. System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip git
```

Make sure your user is in the `dialout` group so the app can open `/dev/ttyUSB0`:

```bash
groups        # check that 'dialout' is in the list
# if not:
sudo usermod -aG dialout $USER
# then log out and back in for the group change to take effect
```

---

## 3. Install the tool

```bash
git clone https://github.com/simonpasley/pylontech-battery-health.git
cd pylontech-battery-health
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Quick sanity check:

```bash
python3 app.py
# open http://<hostname>.local:8080 from another machine on the LAN
# Ctrl-C when you've confirmed it loads
```

---

## 4. Run on boot via systemd

Create the unit file:

```bash
sudo tee /etc/systemd/system/pylontech-health.service > /dev/null <<'EOF'
[Unit]
Description=Pylontech Battery Health Check
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=/home/__USER__/pylontech-battery-health
ExecStart=/home/__USER__/pylontech-battery-health/venv/bin/python3 /home/__USER__/pylontech-battery-health/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Replace __USER__ with your actual username:
sudo sed -i "s/__USER__/$USER/g" /etc/systemd/system/pylontech-health.service

sudo systemctl daemon-reload
sudo systemctl enable --now pylontech-health
sudo systemctl status pylontech-health
```

Tail the logs if anything looks off:

```bash
journalctl -u pylontech-health -f
```

---

## 5. (Optional) Remote access via Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# follow the browser auth link, log in to your tailnet
tailscale status
```

The Pi will then be reachable from any other tailnet device at `http://<hostname>:8080` (Tailscale's MagicDNS handles the name) without exposing the port to the public internet.

If you don't use Tailscale, any of WireGuard / OpenVPN / Cloudflare Tunnel / SSH port-forward will work just as well — the app speaks plain HTTP on `:8080` and doesn't care how you reach it.

> **Don't expose the Pi directly to the public internet.** The app has no authentication. Keep it behind a VPN, SSH tunnel, or your LAN.

---

## 6. Plug in the cable

USB-RS232 cable: USB end into any Pi USB port; RJ45 end into the **master pack's console port** (NOT the CAN port). Open the tool from your laptop / phone, pick `/dev/ttyUSB0` from the dropdown, click **Connect to battery**.

That's it — the rack is now monitorable from anywhere on your tailnet (or VPN of choice).

---

## Updating the tool

```bash
ssh <user>@<hostname>
cd pylontech-battery-health
git pull
sudo systemctl restart pylontech-health
```

---

## Multi-site deployments

If you flash a Pi for each customer site, the only things that need to change per Pi are:

- **Hostname** (so they don't all clash on Tailscale / mDNS)
- **Tailscale auth** (run `sudo tailscale up` once per Pi)

Everything else — the app, the systemd unit, the cable wiring — is identical site-to-site.
