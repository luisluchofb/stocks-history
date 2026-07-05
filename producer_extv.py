#!/usr/bin/env python3
"""Productor EXTENDED-TV: panel PRE/POSTMARKET de MERCADO COMPLETO (scanner TradingView).
Provenance: TV-EXTENDED-RAW (~~ efimero, provisional; JAMAS alimenta historico — capa no-consolidable, mismo espiritu que TEMP-TV).
Naturaleza: historia de la sesion extendida que ningun proveedor de disco reconstruye.
Schema MINIMALISTA propio (14 col, Anexo 6.11): SOLO historia de precio/volumen extendido.
  NO lleva RSI/ATR/MC/VWAP — eso es ANALISIS, no historia, y no cambia entre snapshots del mismo dia.
Escribe SOLO en EXTENDED-TV/ con nombre PREMKT-AAAAMMDD-HHMM.csv o POSTMKT-... (el reloj ET elige el prefijo).
Guarda horaria POR CONSTRUCCION: fuera de las dos ventanas utiles -> exit 0 sin escribir (la Action no falla).
NO dedupe con historico, NO DELISTED (son del consolidado). Purga = MANUAL (Lucho, a criterio).
Uso: python producer_extv.py [america]

────────────────────────────────────────────────────────────────────────
VERIFICAR EN SECO ANTES DE FASE 2 (norma A — dato de pantalla nace ~):
  El productor TEMP-TV probado SOLO usa 'premarket_change' y 'postmarket_change'.
  Los OTROS 6 campos extendidos (precio/gap/volumen/high/low por lado) NO estan
  verificados contra el scanner. Nombres candidatos marcados [~] abajo.
  El guion en seco (`python3 producer_extv.py` en ventana US extendida) confirma:
    - si TV acepta los nombres  -> filas activas > 0, celdas pobladas.
    - si TV los ignora (null)    -> 0 filas activas -> exit sin escribir -> revisar nombres.
    - si TV rechaza la columna   -> urlopen lanza -> Action roja -> revisar nombres.
  Cualquiera de los tres surface el problema. NO promover a cron hasta filas activas OK.
────────────────────────────────────────────────────────────────────────
"""
import json, sys, datetime, pathlib, urllib.request
from zoneinfo import ZoneInfo

MARKET = sys.argv[1] if len(sys.argv) > 1 else "america"
CFG = {
    # min_active = suelo de cordura POST-filtro (la sesion extendida es fina por
    # naturaleza: cientos de nombres, no miles). 0 activos = off-hours/roto -> no escribe.
    "america": {"out": "EXTENDED-TV", "exch": ["NYSE", "NASDAQ", "AMEX"], "min_active": 5},
}[MARKET]

# ── GUARDA HORARIA (ET, DST automatico via zoneinfo) ────────────────────
# El reloj de Nueva York decide el prefijo; el sello del nombre va en UTC (consistencia 6.7).
now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
if now_et.weekday() >= 5:                       # sab/dom: no hay sesion extendida
    print(f"fin de semana ({now_et:%a %H:%M ET}) — no scrapea"); sys.exit(0)
tm = now_et.hour * 60 + now_et.minute
PREMKT  = (7*60,     9*60+25)                    # 07:00 → 09:25 ET (margen 5' antes de apertura)
POSTMKT = (16*60+5,  19*60)                      # 16:05 → 19:00 ET (margen 5' tras cierre)
if   PREMKT[0]  <= tm < PREMKT[1]:  SIDE = "PREMKT"
elif POSTMKT[0] <= tm < POSTMKT[1]: SIDE = "POSTMKT"
else:
    print(f"fuera de ventana extendida ({now_et:%H:%M ET}) — no scrapea"); sys.exit(0)

# ── Columnas del scanner (13 -> 13 valores + timestamp = schema-14) ──────
# [OK] = usado y verificado en producer_tempv.py.  [~] = nombre candidato, VERIFICAR en seco.
TV_COLS = [
    "name",                    # [OK] ticker
    "close",                   # [OK] ref_close: en premkt = cierre previo; en postmkt = cierre de hoy (base del gap)
    "premarket_close",         # [~]  pre_price   (ultimo precio en premarket)
    "premarket_change",        # [OK] pre_chg
    "premarket_gap",           # [~]  pre_gap     (gap vs cierre previo)
    "premarket_volume",        # [~]  pre_vol
    "premarket_high",          # [~]  pre_high
    "premarket_low",           # [~]  pre_low
    "postmarket_close",        # [~]  post_price
    "postmarket_change",       # [OK] post_chg
    "postmarket_volume",       # [~]  post_vol
    "postmarket_high",         # [~]  post_high
    "postmarket_low",          # [~]  post_low
]

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

# El scanner devuelve TODO el mercado; la sesion extendida solo tiene vida en una fraccion.
# Filtramos al lado ACTIVO segun la ventana (premkt o postmkt) por precio o volumen presente.
PRICE, VOL = (f"{SIDE.lower().replace('mkt','market')}_close",
              f"{SIDE.lower().replace('mkt','market')}_volume")   # premarket_close/_volume o postmarket_...

def presente(x): return isinstance(x, (int, float)) and x not in (0, 0.0)

rows = {}
for item in scan(MARKET):
    d = dict(zip(TV_COLS, item.get("d", [])))
    name = str(d.get("name") or "").upper()
    if not name or name in rows:
        continue
    if presente(d.get(PRICE)) or presente(d.get(VOL)):    # solo nombres con vida en ESTE lado
        rows[name] = d

if len(rows) < CFG["min_active"]:
    # exit 0 (no fail): sesion vacia/off-hours, o nombres de campo [~] mal -> revisar en seco.
    print(f"[{SIDE}] {len(rows)} nombres activos < {CFG['min_active']} — no escribe "
          f"(sesion vacia o campos [~] a verificar).")
    sys.exit(0)

def r2(x):  return round(x, 2) if isinstance(x, (int, float)) else ""
def i0(x):  return int(x) if isinstance(x, (int, float)) else ""

utc = datetime.datetime.now(datetime.timezone.utc)
stamp = utc.strftime("%Y%m%d-%H%M")             # AAAAMMDD-HHMM (UTC) — purga por prefijo de fecha
ts_col = utc.strftime("%Y-%m-%dT%H:%MZ")        # timestamp_utc por fila (schema-14 lo lleva; TEMP-TV no)

# Schema de salida EXTENDED (14 col). Se puebla SOLO el lado activo; el otro lado va vacio,
# para no arrastrar dato rancio de la sesion cruzada (un POSTMKT no debe mostrar el premkt de la manana).
HDR = ("ticker,ref_close,pre_price,pre_chg,pre_gap,pre_vol,pre_high,pre_low,"
       "post_price,post_chg,post_vol,post_high,post_low,timestamp_utc")

def fila(t, d):
    ref = r2(d.get("close"))
    if SIDE == "PREMKT":
        pre  = [r2(d.get("premarket_close")), r2(d.get("premarket_change")), r2(d.get("premarket_gap")),
                i0(d.get("premarket_volume")), r2(d.get("premarket_high")), r2(d.get("premarket_low"))]
        post = ["", "", "", "", ""]             # post vacio en captura de premarket
    else:  # POSTMKT
        pre  = ["", "", "", "", "", ""]         # pre vacio en captura de postmarket
        post = [r2(d.get("postmarket_close")), r2(d.get("postmarket_change")),
                i0(d.get("postmarket_volume")), r2(d.get("postmarket_high")), r2(d.get("postmarket_low"))]
    return [t, ref] + pre + post + [ts_col]

cuerpo = "\n".join(",".join(str(x) for x in fila(t, rows[t])) for t in sorted(rows))
outdir = pathlib.Path(CFG["out"]); outdir.mkdir(exist_ok=True)
out = outdir / f"{SIDE}-{stamp}.csv"
out.write_text(HDR + "\n" + cuerpo + "\n", encoding="utf-8")
print(f"OK extended {SIDE} {stamp} [{MARKET}]: {len(rows)} nombres activos -> {out}")
print("~~ EXTENDED-TV efimero (no consolida a historico): purga MANUAL (Lucho).")
