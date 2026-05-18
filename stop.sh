#!/bin/bash
# Zastavení AP Hotspotu – Kali

set -e

WAN_IF="eth0"
AP_IF="wlan0"
AP_IP="192.168.50.1"

if [ "$EUID" -ne 0 ]; then
    echo "Spusť jako root: sudo ./stop.sh"
    exit 1
fi

echo "=== Zastavení AP Hotspotu ==="

echo "1. Zastavení hostapd..."
pkill -F /run/hostapd_ap.pid 2>/dev/null || pkill hostapd 2>/dev/null || true
echo "   ✓ hostapd zastaven"

echo "2. Zastavení dnsmasq..."
systemctl stop dnsmasq || true

echo "3. Vyčištění NAT pravidel..."
iptables -t nat -D POSTROUTING -o "$WAN_IF" -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i "$AP_IF"  -o "$WAN_IF" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i "$WAN_IF" -o "$AP_IF"  -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
echo "   ✓ iptables vyčištěny"

echo "4. Vypnutí IP Forwarding..."
sysctl -w net.ipv4.ip_forward=0

echo "5. Čištění $AP_IF a vrácení NM..."
ip addr del "$AP_IP/24" dev "$AP_IF" 2>/dev/null || true
nmcli dev set "$AP_IF" managed yes 2>/dev/null || true
echo "   ✓ $AP_IF vrácen NetworkManageru"

echo "✓ AP Hotspot zastaven"
