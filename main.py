from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from cachetools import TTLCache
import yfinance as yf
import requests
import pandas as pd

app = FastAPI(title="ETF Backtester API", version="1.0.0")

# --- CONFIGURACIÓN DE CORS ---
# Fundamental para que el navegador de la SPA (Netlify) no bloquee la petición.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, cámbialo a tu dominio ["https://tu-netlify.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CACHÉ EN MEMORIA ---
# Evita que tu servidor sea bloqueado por Yahoo guardando resultados 1 hora (3600 seg)
history_cache = TTLCache(maxsize=1000, ttl=3600)
search_cache = TTLCache(maxsize=1000, ttl=3600)


@app.get("/api/search")
def search_ticker(q: str):
    """
    Busca ETFs en Yahoo Finance. Usa requests porque yfinance no tiene buen buscador integrado.
    """
    if q in search_cache:
        return {"results": search_cache[q]}

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=8"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        return {"results": []}

    data = resp.json()
    results = []
    if "quotes" in data:
        for quote in data["quotes"]:
            if quote.get("quoteType") in ["ETF", "MUTUALFUND", "EQUITY"]:
                results.append({
                    "isin": quote.get("symbol"),
                    "ticker": quote.get("symbol"),
                    "name": quote.get("shortname") or quote.get("longname") or quote.get("symbol"),
                    "assetClass": quote.get("typeDisp") or quote.get("quoteType") or "ETF",
                    "ter": "N/D"
                })

    search_cache[q] = results
    return {"results": results}


@app.get("/api/history")
def get_history(ticker: str, startYear: str, endYear: str):
    """
    Descarga el histórico mensual usando yfinance y lo formatea para la SPA Híbrida.
    """
    cache_key = f"{ticker}_{startYear}_{endYear}"
    if cache_key in history_cache:
        return {"history": history_cache[cache_key]}

    start_date = f"{startYear}-01-01"
    end_date = f"{int(endYear)+1}-01-01"

    try:
        # Descarga mensual
        df = yf.download(ticker, start=start_date, end=end_date, interval="1mo", progress=False)
        
        if df.empty:
            raise HTTPException(status_code=404, detail="No se encontraron datos")

        history = {}
        
        # yfinance puede devolver "Adj Close" o "Close" dependiendo del activo
        if "Adj Close" in df:
            prices = df["Adj Close"]
        elif "Close" in df:
            prices = df["Close"]
        else:
            raise HTTPException(status_code=404, detail="Columna de precio no disponible")

        # Si yfinance devuelve un DataFrame multinivel, nos quedamos con la primera columna
        if isinstance(prices, pd.DataFrame):
            prices = prices.iloc[:, 0]

        # Quitar los valores NaN
        prices = prices.dropna()

        # Generar formato "YYYY-MM" para el Frontend (SPA)
        for date, val in prices.items():
            month_str = f"{date.year}-{str(date.month).zfill(2)}"
            history[month_str] = float(val)

        history_cache[cache_key] = history
        return {"history": history}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
