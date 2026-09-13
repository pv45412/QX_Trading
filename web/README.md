# Scanner React Dashboard

Read-only migration of the Relative Strength page. Streamlit remains unchanged.
No scans, provider requests, configuration writes or trading endpoints are exposed.
The API opens the existing SQLite database read-only and returns a restricted projection.

From SCANNER install `python -m pip install -e ".[web]"`, then run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn qx.interfaces.web:app --host 127.0.0.1 --port 8510
```

From QX/web run `npm ci` and `npm run dev`. Open http://127.0.0.1:5174.
Vite proxies /api to the loopback backend. Keep both services loopback-only.
`npm run build` creates the production frontend bundle; deployment is not configured.

Refresh reloads the saved snapshot; it does not fetch market data. Create snapshots
in Streamlit. RS-line history, holdings, correction-period and down-day metrics
remain unavailable until validated backend coverage exists. React is currently
JavaScript; TypeScript migration and automated browser coverage remain follow-up work.
