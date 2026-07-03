#!/usr/bin/env python3
"""Productor DIAS-TV: panel de CIERRE de MERCADO COMPLETO (scanner TradingView).
(ex-LIVE; renombrado a DIAS-TV para marcar naturaleza: cierres del dia, fuente TV.)
Provenance: TV-LIVE-RAW (sin ajustar). Sin universe.txt [G-D]: barrido con
filtros; la watchlist filtra al LEER. Columnas TV = ~ hasta piloto P150.b.
Uso: python producer_live.py [america|germany|spain|italy|france|uk]"""
import json, sys, datetime, pathlib, urllib.request

MARKET = sys.argv[1] if len(sys.argv) > 1 else "america"
CFG = {  # exchanges EU = ~ verificar en piloto P152
    "america": {"out": "DIAS-TV", "exch": ["NYSE", "NASDAQ", "AMEX"], "min_rows": 6000},
    "germany": {"out": "LIVE-EU", "exch": ["XETR"],        "min_rows": 300},
    "spain":   {"out": "LIVE-EU", "exch": ["BME"],         "min_rows": 80},
    "italy":   {"out": "LIVE-EU", "exch": ["MIL"],         "min_rows": 150},
    "france":  {"out": "LIVE-EU", "exch": ["EURONEXTPAR"], "min_rows": 200},
    "uk":      {"out": "LIVE-EU", "exch": ["LSE"],         "min_rows": 300},
}[MARKET]

TV_COLS = ["name","open","close","change","gap","volume","relative_volume_10d_calc",
           "Perf.W","Perf.1M","Perf.3M","Perf.6M","Perf.YTD",
           "RSI","Volatility.M","ATR","SMA50","SMA200","price_52_week_high"]

def scan(market, chunk=8000):
    filt = [{"left": "exchange", "operation": "in_range", "right": CFG["exch"]}]
    out, start = [], 0
    while True:
        payload = {"columns": TV_COLS, "options": {"lang": "en"}, "markets": [market],
                   "filter": filt, "range": [start, start + chunk],
                   "sort": {"sortBy": "name", "sortOrder": "asc"}}
        req = urllib.request.Request(
            f"https://scanner.tradingview.com/{market}/scan",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        batch = json.load(urllib.request.urlopen(req, timeout=120)).get("data", [])
        out += batch
        if len(batch) < chunk:
            return out
        start += chunk

rows = {}
for item in scan(MARKET):
    d = dict(zip(TV_COLS, item.get("d", [])))
    name = str(d.get("name") or "").upper()
    if name and name not in rows:
        rows[name] = d
if len(rows) < CFG["min_rows"]:
    sys.exit(f"ABORT sin escribir [{MARKET}]: {len(rows)} filas < {CFG['min_rows']} minimas — panel incompleto")

def r2(x): return round(x, 2) if isinstance(x, (int, float)) else ""
def dist(a, b):
    return round((a / b - 1) * 100, 2) if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b else ""

hoy = datetime.date.today().isoformat()   # cron en UTC = fecha de sesion US
HDR = ("ticker,open,close,chg_pct,gap_pct,vol,relvol,perf_1w,perf_1m,perf_3m,"
       "perf_6m,perf_ytd,rsi14,volatility_1m,atr14_pct,dist_sma50,dist_sma200,pct_52wh")
pref = "" if MARKET == "america" else CFG["exch"][0] + "_"

def fila(t, d):
    c = d.get("close")
    atr = round(d["ATR"] / c * 100, 2) if isinstance(d.get("ATR"), (int, float)) and c else ""
    vol = d.get("volume"); vol = int(vol) if isinstance(vol, (int, float)) else ""
    return [pref + t, r2(d.get("open")), r2(c), r2(d.get("change")), r2(d.get("gap")),
            vol, r2(d.get("relative_volume_10d_calc")),
            r2(d.get("Perf.W")), r2(d.get("Perf.1M")), r2(d.get("Perf.3M")),
            r2(d.get("Perf.6M")), r2(d.get("Perf.YTD")), r2(d.get("RSI")),
            r2(d.get("Volatility.M")), atr,
            dist(c, d.get("SMA50")), dist(c, d.get("SMA200")),
            dist(c, d.get("price_52_week_high"))]

cuerpo = "\n".join(",".join(str(x) for x in fila(t, rows[t])) for t in sorted(rows))
outdir = pathlib.Path(CFG["out"]); outdir.mkdir(exist_ok=True)
previos = sorted(outdir.glob("CIERRE-*.csv"))
if previos:
    ult = previos[-1].read_text(encoding="utf-8")
    if ult.split("\n", 1)[1].strip() == cuerpo.strip():
        print(f"ECO-FESTIVO [{MARKET}] {hoy}: panel identico a {previos[-1].name} — no escribo")
        sys.exit(0)
    antes = {l.split(",")[0] for l in ult.strip().split("\n")[1:] if l.strip()}
    hoy_set = {pref + t for t in rows}
    dl = pathlib.Path("DELISTED.csv")
    ya = set()
    if dl.exists():
        ya = {l.split(",")[0] for l in dl.read_text(encoding="utf-8").splitlines()[1:] if l.strip()}
    desap = sorted((antes - hoy_set) - ya)
    if desap:
        existia = dl.exists()
        with open(dl, "a", encoding="utf-8") as f:
            if not existia:
                f.write("ticker,last_seen\n")
            fecha_prev = previos[-1].stem[7:]
            f.writelines(f"{t},{fecha_prev}\n" for t in desap)
        print(f"DELISTED +{len(desap)}: {desap[:10]}")

out = outdir / f"CIERRE-{hoy}.csv"
out.write_text(HDR + "\n" + cuerpo + "\n", encoding="utf-8")
print(f"OK {hoy} [{MARKET}]: {len(rows)} filas -> {out}")
