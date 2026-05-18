# wifi-foward-lan--AP

Kali Linux jako softwarový AP — internet z kabelu (eth0) sdílený přes USB WiFi dongle (wlan0).

## Topologie

```
Internet
   │
[eth0] ← kabel
   │
 Kali Linux (NAT + hostapd + dnsmasq)
   │
[wlan0] ← USB WiFi dongle (RTL8188GU) jako AP
   │
 WiFi klienti (192.168.50.x)
```

## Požadavky

- USB WiFi adapter s podporou AP módu (ověř: `iw list | grep "AP"`)
- `hostapd`, `dnsmasq` nainstalované
- eth0 s internetem

```bash
sudo apt install hostapd dnsmasq
```

## Konfigurace

### hostapd.conf
```
ssid=NazevSite
wpa_passphrase=TvojeHeslo
channel=6
```

### dnsmasq.conf
- DHCP rozsah: `192.168.50.10 – 192.168.50.100`
- Gateway + DNS: `192.168.50.1` (Kali)

## Spuštění

```bash
sudo ./setup.sh
```

## Zastavení

```bash
sudo ./stop.sh
# wlan0 se vrátí NetworkManageru
```

## Web UI

```bash
cd webui && python3 app.py
# → http://localhost:8080
```

Funkce: spustit/zastavit AP, změnit SSID/heslo, zobrazit připojené klienty.

## Diagnostika

```bash
# Stav AP
pgrep -a hostapd

# Připojení klienti (DHCP leases)
cat /var/lib/misc/dnsmasq.leases

# NAT pravidla
sudo iptables -t nat -L POSTROUTING -v

# Provoz
sudo tcpdump -i wlan0 -n
sudo tcpdump -i eth0 -n
```

## Soubory

| Soubor | Popis |
|--------|-------|
| `setup.sh` | Spustí AP (hostapd, dnsmasq, NAT) |
| `stop.sh` | Zastaví AP, vrátí wlan0 NM |
| `hostapd.conf` | SSID, heslo, kanál |
| `dnsmasq.conf` | DHCP + DNS pro klienty |
| `webui/app.py` | Web UI na localhost:8080 |
