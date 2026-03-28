# HackNewHaven — Preflight API (Economic Navigation Pilots)

This repository contains a small FastAPI service that looks up airports from a CSV and exposes a `/weather/{code}` endpoint which fetches METAR data from aviationweather.gov. The endpoint accepts either a 3-letter IATA code (e.g. `JFK`) or an ICAO code (e.g. `KJFK`) and will attempt to resolve IATA→ICAO using the included airport dataset.

**Files of interest**
- [backend/main.py](backend/main.py#L1) — FastAPI app and `/weather/{code}` endpoint.
- [backend/services/weather_service.py](backend/services/weather_service.py#L1) — METAR client (`get_metar`).
- [backend/services/airport_service.py](backend/services/airport_service.py#L1) — IATA/ICAO lookup backed by `data/airports.csv`.
- [requirements.txt](requirements.txt#L1) — Python dependencies.

**Prerequisites**
- Python 3.10 or newer
- PowerShell or CMD on Windows (instructions below are PowerShell-focused)

Setup and run (Windows PowerShell)

1. Open PowerShell and change to the project folder:

```powershell
cd "CODE_REPOSITORY_LOCATION"
```

2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# (If using cmd.exe: .\.venv\Scripts\activate)
```

3. Upgrade pip and install requirements:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Run the FastAPI app with Uvicorn:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Quick tests

- Open the interactive docs in a browser: http://127.0.0.1:8000/docs
- Test with `curl` (IATA → resolved ICAO returned in response):

```powershell
curl http://127.0.0.1:8000/weather/JFK
curl http://127.0.0.1:8000/weather/KJFK
```

- Run the included tiny test script that directly calls the aviationweather API (example file at repository root):

```powershell
python .py
```

Module-level test (directly call the service)

If you prefer to test the `weather_service` module directly:

```powershell
python - <<'PY'
import sys, os, json
sys.path.insert(0, os.path.join(r".", "backend"))
from services.weather_service import get_metar
print(json.dumps(get_metar("KJFK"), indent=2))
PY
```

Notes & troubleshooting

- The project already lists `requests` and `uvicorn` in `requirements.txt`.
- If the airport CSV does not contain an IATA code, the endpoint will fall back to using the provided code as-is.
- If you see network/timeout errors when calling the METAR API, confirm your machine has internet access and retry.

Want more?

- I can add a unit test file for the lookup and the `/weather` endpoint, or add a heuristic fallback (for US airports, prefix `K` to the IATA code) — tell me which you prefer.

**Excluding the virtual environment from commits**

- This project already includes a `.gitignore` entry for common virtual environment folders (for example `.venv/` and `venv/`). If you want to confirm, open the file at the repository root: `.gitignore`.
- If you accidentally committed the `.venv` folder already, you can stop tracking it and remove it from the index while keeping the files locally:

```powershell
git rm -r --cached .venv
git commit -m "Stop tracking virtual environment"
git push
```

- After that, ensure `.venv/` is listed in `.gitignore` so it won't be committed again.

