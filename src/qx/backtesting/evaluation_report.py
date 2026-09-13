"""Content-addressed evaluation reports; filesystem writes require an explicit save call."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isclose
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal  # type: ignore[import-untyped]
import pydantic

from qx.backtesting.evaluation_protocol import (
    EvaluationPhase,
    EvaluationProtocol,
    EvaluationSnapshot,
    evaluate_phase,
    holdout_start,
    normalize_symbols,
)
from qx.data.providers import REQUIRED_COLUMNS
from qx.models.backtest import BacktestParameters, BacktestRunResult, BacktestTrade
from qx.models.scan import RectangleScanParameters

REPORT_DIRECTORY = Path("data/evaluation_reports")
SCHEMA_VERSION = 1
MAX_SAVED_REPORT_BYTES = 50_000_000
LIMITATIONS = [
    "Exploratory historical simulation only. No performance guarantees or validated trading edge.",
    "Repeated inspection or rerunning after seeing holdout results contaminates the holdout; use new unseen data for further validation.",
    "Current membership is not historical membership; survivorship bias is unverified.",
    "Daily bars cannot establish intrabar execution order. Stop-first ambiguous bars, gap-aware fills, capped targets; illustrative fees and slippage, no market impact or capacity model.",
    "Mean net trade return is not portfolio return. Trades across symbols may overlap and are not independent.",
    "Cached bar freshness, corporate-action adjustment and provider accuracy are not independently verified.",
    "Date checks use a NYSE reference calendar and the recorded capture date, not proof of instrument-specific sessions or completed daily closes. This is not prospective validation.",
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def content_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def implementation_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    paths = [*root.joinpath("backtesting").glob("*.py"), *root.joinpath("patterns").glob("*.py"),
             root / "models/backtest.py", root / "models/scan.py"]
    sources = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
               for path in sorted(paths)}
    return {"sources": sources, "python": platform.python_version(), "pandas": pd.__version__,
            "numpy": np.__version__, "pydantic": pydantic.__version__,
            "pandas_market_calendars": mcal.__version__}


def evaluation_spec(
    symbols: list[str], *, universe: str, period: str, profile: str,
    scan_parameters: RectangleScanParameters, parameters: BacktestParameters,
    protocol: EvaluationProtocol, kind: str = "fixed_holdout",
    grid: dict[str, list[float] | list[int]] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind, "universe": {"name": universe, "exact_symbols": normalize_symbols(symbols)},
        "period": period, "interval": "1d", "data_source": "frozen_daily_bars",
        "profile": profile, "scan_parameters": scan_parameters.model_dump(mode="json"),
        "backtest_parameters": parameters.model_copy(update={"evaluation_fraction": 1.0}).model_dump(mode="json"),
        "costs": {"fee_bps_per_side": parameters.fee_bps_per_side,
                  "slippage_bps_per_side": parameters.slippage_bps_per_side},
        "protocol": protocol.model_dump(mode="json"), "grid": grid,
        "implementation": implementation_identity(),
    }


def snapshot_payload(snapshot: EvaluationSnapshot) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for symbol in snapshot.symbols:
        bars = snapshot.bars_by_symbol.get(symbol)
        if bars is None:
            records.append({"symbol": symbol, "status": snapshot.failures[symbol]})
            continue
        values = bars.to_numpy(dtype=float)
        inputs: dict[str, Any] = {
            "columns": list(bars.columns), "dates": [str(date) for date in bars.index],
            "values": [[float(value) if np.isfinite(value) else None for value in row] for row in values],
        }
        provenance = bars.attrs.get("provenance", {})
        records.append({"symbol": symbol, "status": "captured", "input_sha256": content_hash(inputs),
                        "history_start": inputs["dates"][0], "asof": inputs["dates"][-1],
                        "bar_count": len(bars), "actual_source": provenance.get("actual_source", "unknown"),
                        "retrieved_at": provenance.get("retrieved_at"), "inputs": inputs,
                        "date_validation": snapshot.date_checks.get(symbol, {})})
    return {"symbols": records, "sha256": content_hash(records)}


def restore_snapshot(payload: dict[str, Any]) -> EvaluationSnapshot:
    records = payload["symbols"]
    if payload["sha256"] != content_hash(records):
        raise ValueError("Evaluation input digest mismatch")
    symbols = [record["symbol"] for record in records]
    if any(not isinstance(symbol, str) for symbol in symbols) or normalize_symbols(symbols) != symbols:
        raise ValueError("Evaluation symbols must be normalized, unique and ordered")
    frames, failures, date_checks = {}, {}, {}
    for record in records:
        symbol = record["symbol"]
        if record["status"] != "captured":
            failures[symbol] = record["status"]
            continue
        inputs = record["inputs"]
        if record["input_sha256"] != content_hash(inputs):
            raise ValueError("Symbol input digest mismatch")
        bars = pd.DataFrame(inputs["values"], columns=inputs["columns"],
                            index=pd.DatetimeIndex(inputs["dates"]), dtype=float)
        if (list(bars.columns) != REQUIRED_COLUMNS or bars.empty or bars.index.hasnans
                or not bars.index.is_unique or not bars.index.is_monotonic_increasing
                or len(bars) != record["bar_count"] or str(bars.index[0]) != record["history_start"]
                or str(bars.index[-1]) != record["asof"]):
            raise ValueError("Invalid recorded bar window")
        bars.attrs["provenance"] = {"actual_source": record["actual_source"],
                                    "retrieved_at": record["retrieved_at"]}
        frames[symbol] = bars
        date_checks[symbol] = record.get("date_validation", {})
    return EvaluationSnapshot([row["symbol"] for row in records], frames, failures, date_checks)


def phase_payload(phase: EvaluationPhase | None) -> dict[str, Any] | None:
    if phase is None:
        return None
    result = phase.result
    return {"result": result.model_dump(mode="json"), "coverage": phase.coverage,
            "warnings": phase.warnings, "mean_net_trade_return": result.average_return_pct if result.total_trades else None,
            "target_hit_rate": result.win_rate if result.total_trades else None,
            "positive_net_trades": sum(trade.return_pct > 0 for item in result.results for trade in item.trades)}


def build_evaluation_report(
    spec: dict[str, Any], snapshot: EvaluationSnapshot, *,
    training: EvaluationPhase | None, heldout: EvaluationPhase | None,
    selected_parameters: BacktestParameters | None, training_rows: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if snapshot.symbols != spec["universe"]["exact_symbols"]:
        raise ValueError("Snapshot symbols do not match the evaluation universe")
    protocol = EvaluationProtocol.model_validate(spec["protocol"])
    split = holdout_start(snapshot, protocol)
    data = snapshot_payload(snapshot)
    warnings = [*LIMITATIONS, *(training.warnings if training else []), *(heldout.warnings if heldout else [])]
    asofs = {row["asof"] for row in data["symbols"] if row["status"] == "captured"}
    if len(asofs) > 1:
        warnings.append("Symbol evidence dates differ; inspect per-symbol coverage and asof dates.")
    if any(row.get("actual_source") == "unknown" for row in data["symbols"]):
        warnings.append("Actual source is unknown for some cached bars; content hashes identify inputs, not source accuracy.")
    if selected_parameters is None:
        warnings.append("No candidate selected: no usable training trades. Holdout was not evaluated.")
    body = {
        "schema_version": SCHEMA_VERSION, "spec": spec, "spec_sha256": content_hash(spec),
        "data": data, "split": {
            "holdout_start": str(split) if split is not None else None,
            "basis": "Sorted union of captured daily labels on/before each recorded ET capture date; future labels excluded from the shared cutoff, raw inputs retained.",
            "training": "Signals, entries and exits strictly before cutoff; full forward horizon reserved.",
            "holdout": "Signals on/after cutoff; earlier bars used only for indicator warm-up; full forward horizon reserved.",
            "selection": ("Training-only ranking; freeze one candidate before a single holdout evaluation."
                          if spec["kind"] == "training_selection" else "Fixed user parameters; no ranking or tuning."),
            "ranking": ("Training mean net trade return descending; ties: more trades, higher setup threshold, shorter entry window."
                        if spec["kind"] == "training_selection" else None),
        },
        "selected_parameters": selected_parameters.model_dump(mode="json") if selected_parameters else None,
        "results": {"training": phase_payload(training), "holdout": phase_payload(heldout),
                    "training_grid": training_rows or []},
        "warnings": warnings,
    }
    return {**body, "report_id": content_hash(body),
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat()}


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)


def _check_numbers(actual: dict[str, Any], expected: dict[str, Any], *, context: str = "summary") -> None:
    for key, value in expected.items():
        supplied = actual.get(key)
        if value is None:
            matches = key in actual and supplied is None
        elif type(value) is int:
            matches = type(supplied) is int and supplied == value
        else:
            matches = (isinstance(supplied, (int, float)) and not isinstance(supplied, bool)
                       and isclose(supplied, value, rel_tol=1e-12, abs_tol=1e-12))
        if not matches:
            raise ValueError(f"Evaluation {context} mismatch: {key}")


def _trade_summary(trades: list[BacktestTrade]) -> dict[str, Any]:
    count = len(trades)
    return {"total_trades": count,
            "win_rate": sum(trade.outcome == "win" for trade in trades) / count if count else 0.0,
            "average_return_pct": sum(trade.return_pct for trade in trades) / count if count else 0.0}


def _validate_phase_summary(payload: dict[str, Any], symbols: list[str], phase: str) -> None:
    run = BacktestRunResult.model_validate(payload["result"])
    coverage = payload["coverage"]
    if (not isinstance(coverage, list) or any(not isinstance(row, dict) for row in coverage)
            or [row.get("symbol") for row in coverage] != symbols
            or any(row.get("phase") != phase for row in coverage)):
        raise ValueError("Evaluation coverage mismatch")
    evaluated = [row for row in coverage if row.get("status") == "evaluated"]
    if ([result.symbol for result in run.results] != [row["symbol"] for row in evaluated]
            or run.failed_symbols != [row["symbol"] for row in coverage if row.get("status") != "evaluated"]):
        raise ValueError("Evaluation coverage/result mismatch")
    for raw, result, row in zip(payload["result"]["results"], run.results, evaluated, strict=True):
        if any(trade.symbol != result.symbol or trade.outcome not in {"win", "loss", "timeout"}
               for trade in result.trades):
            raise ValueError("Evaluation trade identity or outcome mismatch")
        _check_numbers(raw, _trade_summary(result.trades))
        _check_numbers(row, {"trades": len(result.trades)})
    # Validate summaries from recorded trades only; opening a report never reruns a strategy.
    trades = [trade for result in run.results for trade in result.trades]
    totals = _trade_summary(trades)
    _check_numbers(payload["result"], {**totals, "total_symbols": len(symbols)})
    _check_numbers(payload, {
        "mean_net_trade_return": totals["average_return_pct"] if trades else None,
        "target_hit_rate": totals["win_rate"] if trades else None,
        "positive_net_trades": sum(trade.return_pct > 0 for trade in trades),
    })


def validate_report(report: dict[str, Any], spec: dict[str, Any] | None = None) -> None:
    if not isinstance(report, dict):
        raise ValueError("Evaluation report must be an object")
    body = {key: value for key, value in report.items() if key not in {"report_id", "generated_at"}}
    if report["schema_version"] != SCHEMA_VERSION or content_hash(body) != report["report_id"]:
        raise ValueError("Incompatible or damaged evaluation report")
    if content_hash(report["spec"]) != report["spec_sha256"]:
        raise ValueError("Evaluation spec digest mismatch")
    if spec is not None and report["spec"] != spec:
        raise ValueError("Evaluation settings or implementation do not match")
    snapshot = restore_snapshot(report["data"])
    recorded_spec = report["spec"]
    if snapshot.symbols != recorded_spec["universe"]["exact_symbols"]:
        raise ValueError("Evaluation universe mismatch")
    if recorded_spec["kind"] not in {"fixed_holdout", "training_selection"}:
        raise ValueError("Unsupported evaluation kind")
    parameters = BacktestParameters.model_validate(recorded_spec["backtest_parameters"])
    RectangleScanParameters.model_validate(recorded_spec["scan_parameters"])
    protocol = EvaluationProtocol.model_validate(recorded_spec["protocol"])
    split = holdout_start(snapshot, protocol)
    if report["split"]["holdout_start"] != (str(split) if split is not None else None):
        raise ValueError("Evaluation split mismatch")
    if recorded_spec["costs"] != {"fee_bps_per_side": parameters.fee_bps_per_side,
                                  "slippage_bps_per_side": parameters.slippage_bps_per_side}:
        raise ValueError("Evaluation costs mismatch")
    if report["selected_parameters"] is not None:
        BacktestParameters.model_validate(report["selected_parameters"])
        _check_numbers(report["selected_parameters"], recorded_spec["costs"], context="costs")
    created = datetime.fromisoformat(report["generated_at"])
    if created.tzinfo is None:
        raise ValueError("Report creation timestamp must include a timezone")
    for phase in ("training", "holdout"):
        payload = report["results"][phase]
        if payload is not None:
            _validate_phase_summary(payload, snapshot.symbols, phase)


def save_evaluation_report(report: dict[str, Any], directory: Path = REPORT_DIRECTORY) -> Path:
    validate_report(report)
    serialized = report_json(report)
    if len(serialized.encode("utf-8")) > MAX_SAVED_REPORT_BYTES:
        raise ValueError("Report exceeds the 50 MB saved-report limit; JSON export remains available")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report['report_id']}.json"
    if path.exists():
        validate_report(json.loads(path.read_text(encoding="utf-8")), report["spec"])
        return path
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".evaluation-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def latest_compatible_report(
    spec: dict[str, Any], directory: Path = REPORT_DIRECTORY
) -> dict[str, Any] | None:
    if not directory.is_dir():
        return None
    candidates = []
    try:
        for path in directory.glob("*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
    except OSError:
        return None
    spec_hash = content_hash(spec)
    for _, path in sorted(candidates, reverse=True):
        try:
            if path.stat().st_size > MAX_SAVED_REPORT_BYTES:
                continue
            report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or report.get("spec_sha256") != spec_hash:
                continue
            validate_report(report, spec)
            return report
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def evaluate_fixed_snapshot(spec: dict[str, Any], snapshot: EvaluationSnapshot) -> dict[str, Any]:
    scan = RectangleScanParameters.model_validate(spec["scan_parameters"])
    parameters = BacktestParameters.model_validate(spec["backtest_parameters"])
    split = holdout_start(snapshot, EvaluationProtocol.model_validate(spec["protocol"]))
    heldout = evaluate_phase(snapshot, scan, parameters, phase="holdout", split=split)
    return build_evaluation_report(spec, snapshot, training=None, heldout=heldout,
                                   selected_parameters=parameters)


def replay_evaluation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Explicit, offline replay. Refuse to claim reproducibility under different engine code."""
    validate_report(report)
    spec = report["spec"]
    if spec["implementation"] != implementation_identity():
        raise ValueError("Replay requires the recorded implementation and dependency versions")
    snapshot = restore_snapshot(report["data"])
    if spec["kind"] == "fixed_holdout":
        return evaluate_fixed_snapshot(spec, snapshot)
    if spec["kind"] == "training_selection":
        from qx.backtesting.strategy_lab import evaluate_strategy_snapshot

        return evaluate_strategy_snapshot(spec, snapshot).report
    raise ValueError("Unsupported evaluation kind")
