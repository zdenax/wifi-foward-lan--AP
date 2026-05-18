#!/usr/bin/env python3
import subprocess, json, re
from pathlib import Path
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

SCRIPT_DIR     = Path(__file__).parent.parent
SETUP_SCRIPT   = SCRIPT_DIR / "setup.sh"
STOP_SCRIPT    = SCRIPT_DIR / "stop.sh"
HOSTAPD_CONF   = SCRIPT_DIR / "hostapd.conf"
DNSMASQ_LEASES = Path("/var/lib/misc/dnsmasq.leases")

WAN_IF = "eth0"
AP_IF  = "wlan0"

ALIASES_FILE = Path(__file__).parent / "aliases.json"

try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("config_local",
        Path(__file__).parent / "config.local.py")
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    WAN_IF = getattr(cfg, "WAN_IF", WAN_IF)
    AP_IF  = getattr(cfg, "AP_IF",  AP_IF)
except Exception:
    pass


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""

def forwarding_active():
    return run("cat /proc/sys/net/ipv4/ip_forward") == "1"

def hostapd_running():
    return bool(run("pgrep -x hostapd"))

def get_iface_stats(iface):
    try:
        rx = int(Path(f"/sys/class/net/{iface}/statistics/rx_bytes").read_text())
        tx = int(Path(f"/sys/class/net/{iface}/statistics/tx_bytes").read_text())
        return rx, tx
    except Exception:
        return 0, 0

def fmt_bytes(b):
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def get_iface_ip(iface):
    out = run(f"ip addr show {iface}")
    m = re.search(r"inet (\S+)", out)
    return m.group(1) if m else ""

def get_iface_state(iface):
    try:
        return Path(f"/sys/class/net/{iface}/operstate").read_text().strip()
    except Exception:
        return "unknown"

def load_aliases():
    try:
        return json.loads(ALIASES_FILE.read_text())
    except Exception:
        return {}

def save_aliases(aliases):
    ALIASES_FILE.write_text(json.dumps(aliases, ensure_ascii=False, indent=2))

def read_hostapd_conf():
    ssid, psk, channel = "", "", "6"
    try:
        for line in HOSTAPD_CONF.read_text().splitlines():
            if line.startswith("ssid="):
                ssid = line.split("=", 1)[1]
            elif line.startswith("wpa_passphrase="):
                psk = line.split("=", 1)[1]
            elif line.startswith("channel="):
                channel = line.split("=", 1)[1]
    except Exception:
        pass
    return ssid, psk, channel

def write_hostapd_conf(ssid=None, psk=None):
    try:
        lines = HOSTAPD_CONF.read_text().splitlines()
    except Exception:
        return False
    new_lines = []
    for line in lines:
        if ssid is not None and line.startswith("ssid="):
            new_lines.append(f"ssid={ssid}")
        elif psk is not None and line.startswith("wpa_passphrase="):
            new_lines.append(f"wpa_passphrase={psk}")
        else:
            new_lines.append(line)
    HOSTAPD_CONF.write_text("\n".join(new_lines) + "\n")
    return True

def get_clients():
    aliases = load_aliases()
    leases = {}
    if DNSMASQ_LEASES.exists():
        for line in DNSMASQ_LEASES.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mac, ip, hostname = parts[1], parts[2], parts[3]
                leases[ip] = {"mac": mac, "hostname": hostname if hostname != "*" else ""}
    clients = []
    seen = set()
    for ip, info in leases.items():
        seen.add(ip)
        name = aliases.get(ip) or aliases.get(info["mac"]) or info["hostname"] or ""
        clients.append({"ip": ip, "mac": info["mac"], "name": name})
    for line in run(f"ip neigh show dev {AP_IF}").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "lladdr" and "FAILED" not in line:
            ip, mac = parts[0], parts[2]
            if ip not in seen:
                name = aliases.get(ip) or aliases.get(mac) or ""
                clients.append({"ip": ip, "mac": mac, "name": name})
    return clients


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    wan_rx, wan_tx = get_iface_stats(WAN_IF)
    ap_rx,  ap_tx  = get_iface_stats(AP_IF)
    ssid, psk, _ = read_hostapd_conf()
    return jsonify({
        "forwarding": forwarding_active(),
        "wan": {
            "iface": WAN_IF,
            "ip": get_iface_ip(WAN_IF),
            "state": get_iface_state(WAN_IF),
            "rx": fmt_bytes(wan_rx),
            "tx": fmt_bytes(wan_tx),
        },
        "lan": {
            "iface": AP_IF,
            "ip": get_iface_ip(AP_IF),
            "state": get_iface_state(AP_IF),
            "rx": fmt_bytes(ap_rx),
            "tx": fmt_bytes(ap_tx),
        },
        "clients": get_clients(),
        "ap": {
            "model": "RTL8188GU AP",
            "ssid": ssid,
            "password": psk,
            "reachable": hostapd_running(),
        },
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    result = subprocess.run(["sudo", str(SETUP_SCRIPT)], capture_output=True, text=True)
    ok = result.returncode == 0
    return jsonify({"ok": ok, "output": result.stdout + result.stderr})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    result = subprocess.run(["sudo", str(STOP_SCRIPT)], capture_output=True, text=True)
    ok = result.returncode == 0
    return jsonify({"ok": ok, "output": result.stdout + result.stderr})

@app.route("/api/ap/wifi", methods=["POST"])
def api_ap_wifi():
    data = request.get_json()
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "")
    if not ssid:
        return jsonify({"ok": False, "error": "SSID nesmí být prázdné"})
    if password and len(password) < 8:
        return jsonify({"ok": False, "error": "Heslo musí mít min. 8 znaků"})
    write_hostapd_conf(ssid=ssid, psk=password if password else None)
    if hostapd_running():
        subprocess.run(["sudo", "pkill", "-HUP", "hostapd"], capture_output=True)
    return jsonify({"ok": True})

@app.route("/api/aliases", methods=["GET"])
def api_aliases_get():
    return jsonify(load_aliases())

@app.route("/api/aliases", methods=["POST"])
def api_aliases_set():
    data = request.get_json()
    key = data.get("key", "").strip()
    name = data.get("name", "").strip()
    if not key:
        return jsonify({"ok": False, "error": "key required"})
    aliases = load_aliases()
    if name:
        aliases[key] = name
    else:
        aliases.pop(key, None)
    save_aliases(aliases)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
