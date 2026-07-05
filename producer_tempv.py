#!/usr/bin/env python3
"""Productor TEMP-TV: panel INTRADIA de MERCADO COMPLETO (scanner TradingView).
Provenance: TV-INTRADAY-RAW (~~ efimero, provisional; JAMAS alimenta historico).
Naturaleza DISTINTA a DIAS-TV: schema propio de momentum intradia — fuera lo casi-invariable
en sesion (perfs multi-mes, SMA200, 52wh), dentro lo volatil (VWAP, premarket/postmarket,
high/low de sesion, turnover) que el analisis tecnico/momentum usa y ningun historico recoge.
Escribe SOLO en TEMP-TV/ con nombre TEMPTV-AAAAMMDD-HHMM.csv (varios por dia conviven).
NO dedupe, NO DELISTED (son del historico). Purga = MANUAL (Lucho, a criterio).
Campos volatiles (VWAP/premkt/postmkt/turnover) CONFIRMADOS en piloto estructural
3-jul-2026; pendiente solo validar movimiento vivo en sesion (P174.a).
Uso: python producer_tempv.py [america]

────────────────────────────────────────────────────────────────────────
AMPLIACION 4-jul-2026 · schema 18 -> 20 col (Anexo 6.8, cierra frente (a) de P180):
  + rsi5              exhaustion intradia rapida (RSI 14 diluye la señal — caso AVAV 4-jul:
                      RSI 14 = 60,36 mientras RSI 5 = 82,41).
  + chg_from_open_pct momentum real desde la apertura US, separado del gap (caso AVAV:
                      chg total +10,70% = gap +4,53% + sesion desde apertura +5,90%).
  chg_from_open_pct es DERIVADO (last vs open) — NO necesita campo nuevo del scanner.
  rsi5 SI necesita campo del scanner: nombre candidato [~], VERIFICAR EN SECO (ver nota).

VERIFICAR EN SECO (norma A — dato de pantalla nace ~):
  El TEMP-TV probado usa RSI(14) = 'RSI'. El campo de RSI(5) NO esta verificado contra el
  scanner API. Candidato: 'RSI5'. Corre `python3 producer_tempv.py` en sesion US y mira la
  columna rsi5: si viene poblada -> nombre OK; si viene toda vacia -> el string es otro
  (probar variantes) — el valor EXISTE en TV (el filtro manual 'TV Intradia' del 6.10 ya
  muestra RSI 5), solo hay que fijar el identificador del API. NO es bloqueante: si el campo
  falla, rsi5 sale vacio y el resto del panel se escribe igual (celda vacia, no se inventa).
────────────────────────────────────────────────────────────────────────
"""
import json, sys, datetime, pathlib, urllib.request

MARKET = sys.argv[1] if len(sys.argv) > 1 else "america"
CFG = {
    "america": {"out": "TEMP-TV", "exch": ["NYSE", "NASDAQ", "AMEX"], "min_rows": 4000},
}[MARKET]

# Schema INTRADIA propio (20 col). Piloto 3-jul: los 18 originales existen con estos nombres
# del scanner; los 2 nuevos: chg_from_open_pct es derivado (open/last), rsi5 es campo [~].
TV_COLS = [
    "name", "open", "close", "change", "gap",              # precio + % del dia + gap
    "high", "low",                                          # rango de sesion (¿en maximos=fuerza?)
    "volume", "relative_volume_10d_calc",                   # volumen + relvol (rey del momentum)
    "RSI",                                                  # [OK] RSI(14)
    "RSI5",                                                 # [~]  RSI(5) — VERIFICAR EN SECO (ver nota)
    "ATR", "Volatility.M",                                  # volatilidad en curso
    "SMA50",                                                # media que SI se pierde/recupera intradia
    "VWAP",                                                 # el indicador intradia por excelencia
    "premarket_change",                                     # movimiento en extendido (gaps nacen aqui)
    "postmarket_change",                                    # postmercado
    "Value.Traded",                                         # turnover (flujo real $ = filtra pump de centimos)
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

ahora = datetime.datetime.now(datetime.timezone.utc)
stamp = ahora.strftime("%Y%m%d-%H%M")   # AAAAMMDD-HHMM (UTC) → facilita purga por prefijo de fecha
# Schema de salida intradia (20 col; dist_vwap y chg_from_open_pct DERIVADOS con dist()).
HDR = ("ticker,open,last,chg_pct,gap_pct,chg_from_open_pct,high,low,vol,relvol,"
       "rsi14,rsi5,atr14_pct,volatility_1m,dist_sma50,vwap,dist_vwap,premkt_chg,postmkt_chg,turnover_usd")

def fila(t, d):
    c = d.get("close")   # intradia: 'close' del scanner = ULTIMO precio en curso
    op = d.get("open")
    atr = round(d["ATR"] / c * 100, 2) if isinstance(d.get("ATR"), (int, float)) and c else ""
    vol = d.get("volume"); vol = int(vol) if isinstance(vol, (int, float)) else ""
    vwap = d.get("VWAP")
    turn = d.get("Value.Traded"); turn = int(turn) if isinstance(turn, (int, float)) else ""
    return [t, r2(op), r2(c), r2(d.get("change")), r2(d.get("gap")),
            dist(c, op),                                    # chg_from_open_pct (last vs open, derivado)
            r2(d.get("high")), r2(d.get("low")),
            vol, r2(d.get("relative_volume_10d_calc")),
            r2(d.get("RSI")), r2(d.get("RSI5")),            # rsi14, rsi5
            atr, r2(d.get("Volatility.M")),
            dist(c, d.get("SMA50")),
            r2(vwap), dist(c, vwap),
            r2(d.get("premarket_change")), r2(d.get("postmarket_change")), turn]

cuerpo = "\n".join(",".join(str(x) for x in fila(t, rows[t])) for t in sorted(rows))
outdir = pathlib.Path(CFG["out"]); outdir.mkdir(exist_ok=True)
out = outdir / f"TEMPTV-{stamp}.csv"
out.write_text(HDR + "\n" + cuerpo + "\n", encoding="utf-8")
print(f"OK intradia {stamp} [{MARKET}]: {len(rows)} filas -> {out}")
print("~~ TEMP-TV efimero (no consolida a historico): purga MANUAL (Lucho).")
