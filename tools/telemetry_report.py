#!/usr/bin/env python3
"""Puxa a telemetria do tablet (adb) e gera um relatório de saúde/uso.

Uso:
  python3 tools/telemetry_report.py            # puxa via adb para telemetry/<data>/ e analisa
  python3 tools/telemetry_report.py --dir X    # só analisa uma pasta já puxada
"""
import argparse, csv, datetime as dt, glob, os, re, subprocess, sys
from collections import Counter, defaultdict

def pull(dest):
    os.makedirs(dest, exist_ok=True)
    r = subprocess.run(["adb", "pull", "/data/m7s-telemetry/.", dest], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("adb pull falhou: " + r.stderr.strip())

def load_rows(d):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.csv"))):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    r["ts"] = int(r["ts"]); r["uptime_s"] = int(r["uptime_s"])
                    for k in ("batt_pct", "batt_mv", "backlight", "cpu_khz", "cpu_busy_pct", "iowait_pct",
                              "mem_free_kb", "mem_cached_kb", "swap_used_kb", "procs", "wlan_rx_b",
                              "wlan_tx_b", "nand_rd_sect", "nand_wr_sect", "ctxt_delta"):
                        r[k] = int(float(r[k] or 0))
                    rows.append(r)
                except (ValueError, KeyError):
                    pass
    rows.sort(key=lambda r: r["ts"])
    return rows

def fmt_h(s): return f"{s/3600:.1f} h"

def report(d):
    rows = load_rows(d)
    if len(rows) < 2:
        print("Poucos dados ainda."); return
    t0, t1 = rows[0]["ts"], rows[-1]["ts"]
    print(f"# Telemetria M7s — {dt.datetime.fromtimestamp(t0):%d/%m %H:%M} → {dt.datetime.fromtimestamp(t1):%d/%m %H:%M} ({fmt_h(t1-t0)}, {len(rows)} amostras)\n")

    # segmentos entre amostras consecutivas
    on = off = sleep = 0
    drain = {"on": [0, 0], "off": [0, 0]}  # [%perdido, segundos] só descarregando
    boots = 0
    for a, b in zip(rows, rows[1:]):
        wall = b["ts"] - a["ts"]
        if b["uptime_s"] < a["uptime_s"]:
            boots += 1; continue
        upd = b["uptime_s"] - a["uptime_s"]
        state = "on" if a["backlight"] > 0 else "off"
        if state == "on": on += wall
        else: off += wall
        if wall - upd > 5: sleep += wall - upd
        if a["batt_status"] == "Discharging" and b["batt_status"] == "Discharging" and a["usb"] == "0":
            drain[state][0] += a["batt_pct"] - b["batt_pct"]; drain[state][1] += wall
    print("## Energia")
    print(f"- Tela ligada: {fmt_h(on)} · tela desligada: {fmt_h(off)} · sono profundo: {fmt_h(sleep)}"
          + (f" ({100*sleep/max(off,1):.0f}% do tempo com tela off)" if off else ""))
    for k, lab in (("on", "tela ligada"), ("off", "tela desligada")):
        p, s = drain[k]
        if s > 600: print(f"- Consumo com {lab}: {p/(s/3600):.1f} %/h (em {fmt_h(s)} na bateria)")
    print(f"- Bateria agora: {rows[-1]['batt_pct']}% ({rows[-1]['batt_mv']} mV, {rows[-1]['batt_status']}) · reboots no período: {boots}\n")

    print("## CPU e memória (tela ligada)")
    onr = [r for r in rows if r["backlight"] > 0] or rows
    avg = lambda k: sum(r[k] for r in onr) / len(onr)
    freq = Counter(r["cpu_khz"] // 1000 for r in onr)
    print(f"- CPU ocupada média: {avg('cpu_busy_pct'):.0f}% · espera de disco (iowait): {avg('iowait_pct'):.1f}% · load médio: {sum(float(r['load1']) for r in onr)/len(onr):.2f}")
    print("- Frequência: " + ", ".join(f"{f} MHz {100*c/len(onr):.0f}%" for f, c in sorted(freq.items())))
    low = [r for r in onr if r["mem_free_kb"] + r["mem_cached_kb"] < 60000]
    print(f"- RAM livre+cache média: {avg('mem_free_kb')/1024+avg('mem_cached_kb')/1024:.0f} MB · mínimo: {min(r['mem_free_kb']+r['mem_cached_kb'] for r in onr)/1024:.0f} MB · amostras com aperto (<60 MB): {100*len(low)/len(onr):.0f}%")
    print(f"- zRAM usada: média {avg('swap_used_kb')/1024:.0f} MB, pico {max(r['swap_used_kb'] for r in rows)/1024:.0f} MB")
    hot = [r for r in onr if r["cpu_busy_pct"] >= 90]
    print(f"- Amostras com CPU ≥90%: {100*len(hot)/len(onr):.0f}%\n")

    print("## Uso por app (tela ligada, tempo aproximado)")
    by = defaultdict(lambda: [0, 0, 0, 0])  # segundos, soma cpu, soma iowait, n
    for a, b in zip(rows, rows[1:]):
        if a["backlight"] > 0 and a["fg_app"] and b["uptime_s"] >= a["uptime_s"]:
            x = by[a["fg_app"]]; x[0] += b["ts"] - a["ts"]; x[1] += b["cpu_busy_pct"]; x[2] += b["iowait_pct"]; x[3] += 1
    for app, (s, c, w, n) in sorted(by.items(), key=lambda kv: -kv[1][0])[:12]:
        print(f"- {app}: {s/60:.0f} min · CPU média {c/n:.0f}% · iowait {w/n:.1f}%")
    print()

    # rede / disco
    def delta(k):
        tot = 0
        for a, b in zip(rows, rows[1:]):
            dlt = b[k] - a[k]
            if dlt > 0 and b["uptime_s"] >= a["uptime_s"]: tot += dlt
        return tot
    print("## Rede e armazenamento")
    print(f"- Wi-Fi: ↓ {delta('wlan_rx_b')/1e6:.0f} MB · ↑ {delta('wlan_tx_b')/1e6:.0f} MB")
    print(f"- NAND: lidos {delta('nand_rd_sect')*512/1e6:.0f} MB · escritos {delta('nand_wr_sect')*512/1e6:.0f} MB\n")

    print("## Eventos do sistema")
    ev = Counter(); kills = Counter(); crashes = Counter(); anrs = Counter()
    for f in glob.glob(os.path.join(d, "events-*.log")):
        for line in open(f, errors="replace"):
            m = re.search(r"I/(\w+)\(\s*\d+\): \[(.*)\]", line)
            if not m: continue
            tag, body = m.groups(); ev[tag] += 1
            parts = body.split(",")
            if tag == "am_kill" and len(parts) > 2: kills[parts[2]] += 1
            if tag == "am_crash" and len(parts) > 2: crashes[parts[2]] += 1
            if tag == "am_anr" and len(parts) > 2: anrs[parts[2]] += 1
    print("- Contagem: " + ", ".join(f"{k} {v}" for k, v in ev.most_common()))
    if crashes: print("- Crashes: " + ", ".join(f"{k} ({v})" for k, v in crashes.most_common(8)))
    if anrs: print("- Travou (ANR): " + ", ".join(f"{k} ({v})" for k, v in anrs.most_common(8)))
    if kills: print("- Mortos por falta de memória/sistema: " + ", ".join(f"{k} ({v})" for k, v in kills.most_common(8)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    a = ap.parse_args()
    d = a.dir or os.path.join(os.path.dirname(__file__), "..", "telemetry", dt.datetime.now().strftime("%Y%m%d-%H%M"))
    if not a.dir: pull(d)
    report(d)
