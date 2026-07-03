#!/usr/bin/env python3
"""Productor TEMP-TV: panel INTRADIA de MERCADO COMPLETO (scanner TradingView).
Provenance: TV-INTRADAY-RAW (~~ efimero, provisional; JAMAS alimenta historico).
Naturaleza DISTINTA a DIAS-TV: schema propio de momentum intradia — fuera lo casi-invariable
en sesion (perfs multi-mes, SMA200, 52wh), dentro lo volatil (VWAP, premarket/postmarket,
high/low de sesion, turnover) que el analisis tecnico/momentum usa y ningun historico recoge.
Escribe SOLO en TEMP-TV/ con nombre TEMPTV-AAAAMMDD-HHMM.csv (varios por dia conviven).
NO dedupe, NO DELISTED (son del historico). Purga = MANUAL (Lucho, a criterio).
Campos volatiles marcados ~ hasta piloto de validacion (nombres del scanner no-oficial).
Uso: python producer_tempv.py [america]
"""
import json, sys, datetime, pathlib, urllib.request

MARKET = sys.argv[1] if len(sys.argv) > 1 else "america"
CFG = {
    "america": {"out": "TEMP-TV", "exch": ["NYSE", "NASDAQ", "AMEX"], "min_rows": 4000},
}[MARKET]

# Schema INTRADIA propio. Nucleo volatil + generosos (~ = validar en piloto; el scanner
# no-oficial puede usar otro nombre o no exponerlos → la 1a corrida es el piloto).
TV_COLS = [
    "name", "open", "close", "change", "gap",              # precio + % del dia + gap
    "high", "low",                                          # rango de sesion (¿en maximos=fuerza?)
    "volume", "relative_volume_10d_calc",                   # volumen + relvol (rey del momentum)
    "RSI", "ATR", "Volatility.M",                           # osciladores/volatilidad en curso
    "SMA50",                                                # media que SI se pierde/recupera intradia
    "VWAP",                                                 # ~ el indicador intradia por excelencia
    "premarket_change",                                     # ~ movimiento en extendido (gaps nacen aqui)
    "postmarket_change",                                    # ~ postmercado
    "Value.Traded",                                         # ~ turnover (flujo real $ = filtra pump de centimos)
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

ahora = datetime.datetime.utcnow()
stamp = ahora.strftime("%Y%m%d-%H%M")   # AAAAMMDD-HHMM (UTC) → facilita purga por prefijo de fecha
# Schema de salida intradia (18 col volatiles; dist_vwap DERIVADA como dist_sma50)
HDR = ("ticker,open,last,chg_pct,gap_pct,high,low,vol,relvol,rsi14,atr14_pct,"
       "volatility_1m,dist_sma50,vwap,dist_vwap,premkt_chg,postmkt_chg,turnover_usd")

def fila(t, d):
    c = d.get("close")   # intradia: 'close' del scanner = ULTIMO precio en curso
    atr = round(d["ATR"] / c * 100, 2) if isinstance(d.get("ATR"), (int, float)) and c else ""
    vol = d.get("volume"); vol = int(vol) if isinstance(vol, (int, float)) else ""
    vwap = d.get("VWAP")
    turn = d.get("Value.Traded"); turn = int(turn) if isinstance(turn, (int, float)) else ""
    return [t, r2(d.get("open")), r2(c), r2(d.get("change")), r2(d.get("gap")),
            r2(d.get("high")), r2(d.get("low")),
            vol, r2(d.get("relative_volume_10d_calc")), r2(d.get("RSI")), atr,
            r2(d.get("Volatility.M")),
            dist(c, d.get("SMA50")),
            r2(vwap), dist(c, vwap),
            r2(d.get("premarket_change")), r2(d.get("postmarket_change")), turn]

cuerpo = "\n".join(",".join(str(x) for x in fila(t, rows[t])) for t in sorted(rows))
outdir = pathlib.Path(CFG["out"]); outdir.mkdir(exist_ok=True)
out = outdir / f"TEMPTV-{stamp}.csv"
out.write_text(HDR + "\n" + cuerpo + "\n", encoding="utf-8")
print(f"OK intradia {stamp} [{MARKET}]: {len(rows)} filas -> {out}")
print(f"~~ TEMP-TV efimero: purga MANUAL (Lucho). Campos VWAP/premkt/postmkt/turnover = ~ validar en este piloto.")
