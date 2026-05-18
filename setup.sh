#!/bin/bash
# AP Hotspot Setup – Kali
# Internet z eth0 (kabel) → wlan0 (USB dongle jako AP)

set -e

# === Konfigurace ===
WAN_IF="eth0"            # internet (kabel)
AP_IF="wlan0"            # USB dongle → AP
AP_IP="192.168.50.1"     # IP Kali na AP síti
SSID="KaliHotspot"       # upravit v hostapd.conf

echo "=== AP Hotspot Setup (Kali) ==="
echo "    WAN: $WAN_IF (kabel)  →  AP: $AP_IF"

if [ "$EUID" -ne 0 ]; then
    echo "Spusť jako root: sudo ./setup.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Kontrola rozhraní
echo ""
echo "1. Kontrola rozhraní..."
ip link show "$WAN_IF" > /dev/null 2>&1 || { echo "Chyba: $WAN_IF (kabel) nenalezeno"; exit 1; }
ip link show "$AP_IF" > /dev/null 2>&1  || { echo "Chyba: $AP_IF nenalezeno"; exit 1; }

# Ověř internet na WAN
ping -c1 -W3 8.8.8.8 -I "$WAN_IF" > /dev/null 2>&1 || echo "   VAROVÁNÍ: $WAN_IF nemá internet!"

# 2. Odpoj AP_IF od NetworkManageru
echo ""
echo "2. Odpojuji $AP_IF od NetworkManageru..."
nmcli dev disconnect "$AP_IF" 2>/dev/null || true
nmcli dev set "$AP_IF" managed no 2>/dev/null || true

# 3. Statická IP na AP interface
echo ""
echo "3. Nastavuji IP $AP_IP na $AP_IF..."
ip addr flush dev "$AP_IF" 2>/dev/null || true
ip addr add "$AP_IP/24" dev "$AP_IF"
ip link set "$AP_IF" up

# 4. hostapd
echo ""
echo "4. Spouštím hostapd (AP)..."
pkill hostapd 2>/dev/null || true
sleep 1
hostapd -B "$SCRIPT_DIR/hostapd.conf" -P /run/hostapd_ap.pid \
    && echo "   ✓ hostapd spuštěn (SSID: $SSID)" \
    || { echo "   ✗ hostapd selhal"; exit 1; }

# 5. IP Forwarding + NAT
echo ""
echo "5. IP Forwarding + NAT..."
sysctl -w net.ipv4.ip_forward=1
sysctl -w net.ipv4.conf.all.rp_filter=0

iptables -t nat -D POSTROUTING -o "$WAN_IF" -j MASQUERADE 2>/dev/null || true
iptables -t nat -A POSTROUTING -o "$WAN_IF" -j MASQUERADE
iptables -D FORWARD -i "$AP_IF"  -o "$WAN_IF" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i "$WAN_IF" -o "$AP_IF"  -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -i "$AP_IF"  -o "$WAN_IF" -j ACCEPT
iptables -A FORWARD -i "$WAN_IF" -o "$AP_IF"  -m state --state RELATED,ESTABLISHED -j ACCEPT
echo "   ✓ iptables nastaveny"

# 6. dnsmasq (DHCP + DNS pro klienty)
echo ""
echo "6. Nastavení dnsmasq..."

if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
    echo "   Zastavuji systemd-resolved (konflikt port 53)..."
    systemctl stop systemd-resolved
fi

cp "$SCRIPT_DIR/dnsmasq.conf" /etc/dnsmasq.conf
systemctl restart dnsmasq && echo "   ✓ dnsmasq spuštěn" || echo "   ✗ dnsmasq selhal"

# 7. Uložení iptables
echo ""
echo "7. Ukládám iptables pravidla..."
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# 8. Verifikace
echo ""
echo "=== Verifikace ==="
echo "IP Forwarding : $(cat /proc/sys/net/ipv4/ip_forward)"
echo "hostapd PID   : $(cat /run/hostapd_ap.pid 2>/dev/null || echo 'nenalezeno')"
echo "AP IP         : $(ip addr show "$AP_IF" | grep "inet " | awk '{print $2}')"
echo "WAN IP        : $(ip addr show "$WAN_IF" | grep "inet " | awk '{print $2}')"
echo ""
echo "✓ Hotspot aktivní!"
echo "  SSID     : $SSID"
echo "  Heslo    : viz hostapd.conf (wpa_passphrase)"
echo "  AP subnet: 192.168.50.0/24  (gateway: $AP_IP)"
echo "  Zastavení: sudo ./stop.sh"
