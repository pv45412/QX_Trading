# @qx/schwab-plugin

A DeepSeek Harness (DSH) host plugin that wraps the **QX platform's Schwab
broker integration** and the workspace **SMC rules engine** into one desk:

- **Skills** — `schwab-rules-engine`, `schwab-trade-desk`, `schwab-alert-monitor`
  are registered into the session skill catalog (agent + `/name` usable).
- **Tools** — `qx_schwab_status`, `qx_schwab_auth_url`, `qx_schwab_authorize`,
  `qx_schwab_scan`, `qx_schwab_alerts`, `qx_schwab_confirm_trade`.
- **Live dashboard** — `http://127.0.0.1:19387/qx/schwab` (alerts, scan
  results, confirm buttons, OAuth re-authorization).
- **Optional poller** — rescans the watchlist on an interval.

## Data path

The plugin is dependency-free and shells out to
[`python/qx_schwab_worker.py`](python/qx_schwab_worker.py) with the workspace
venv (`C:/Project/2026/.venv/Scripts/python.exe`). The worker reuses
`qx.brokers.schwab` for live quotes/bars and transparently falls back to cached
bars (`data/cache/bars/*_2y.csv`) when Schwab is unavailable, always reporting
the source.

## Scoring model (from `.agents/skills/smc-rules-engine/resources/qx_rules_engine_spec.md`)

```
QX Score = 0.25*SMC + 0.20*Phases + 0.20*CVD_Absorption
         + 0.15*VScore + 0.10*RS_Rank + 0.10*OptionsFlow
score >= 70 -> LONG / BUY CALL   score <= 30 -> SHORT / BUY PUT   else WAIT
```

## Safety

`qx_schwab_confirm_trade` and the dashboard confirm button **stage a paper
order only** and never submit to Schwab. Live execution is fail-closed per
`PROJECT_STATE.md` (milestones EX0–EX3 remain BACKLOG; broker writes are
prohibited until the EX3 live-trading human gate).