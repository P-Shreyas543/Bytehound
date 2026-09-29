"""Diagnostic Run Package Exporter (IMP-11).

Creates reproducible, one-click zip packages containing raw 10 Hz telemetry CSV,
step and cycle summary CSVs, recipe JSON, application log diagnostic slice,
and a cryptographic SHA-256 metadata manifest for engineering sharing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile

from ..config.cycler_config import DEFAULT_LOG_DIR
from ..core.metrics_tracker import CycleSummary, MetricsTracker, StepMetrics
from ..core.profile_model import TestRecipe
from .summary_writer import write_cycle_summary_csv, write_step_summary_csv

logger = logging.getLogger("SingleCellCycler.RunExporter")


def compute_sha256(data: bytes) -> str:
    """Compute hex SHA-256 digest of byte data."""
    return hashlib.sha256(data).hexdigest()


def export_run_package(
    output_zip_path: Optional[str | Path] = None,
    cell_id: int = 1,
    recipe: Optional[TestRecipe] = None,
    raw_csv_path: Optional[str | Path] = None,
    step_history: Optional[List[StepMetrics]] = None,
    cycle_summaries: Optional[List[CycleSummary]] = None,
    app_log_path: Optional[str | Path] = None,
    metrics_tracker: Optional[MetricsTracker] = None,
    operator: str = "Lab Technician",
    test_status: str = "COMPLETED",
    notes: str = "",
    export_dir: str | Path = "single_cell_cycler/exports",
) -> Path:
    """Bundle all run artifacts into an archival .zip package with a manifest.json.

    Parameters
    ----------
    output_zip_path : Optional[str | Path]
        Explicit destination zip file path. If None, auto-generated in `export_dir`.
    cell_id : int
        Active cell channel number (1 or 2).
    recipe : Optional[TestRecipe]
        Active test profile recipe.
    raw_csv_path : Optional[str | Path]
        Path to raw 10 Hz telemetry CSV log file.
    step_history : Optional[List[StepMetrics]]
        List of completed step metrics.
    cycle_summaries : Optional[List[CycleSummary]]
        List of completed cycle summaries.
    app_log_path : Optional[str | Path]
        Path to main cycler application diagnostic text log.
    metrics_tracker : Optional[MetricsTracker]
        Active metrics tracker instance with cumulative throughput.
    operator : str
        Name of testing operator.
    test_status : str
        Execution status ("COMPLETED", "INTERRUPTED", "SAFETY_TRIP", "MANUAL_STOP").
    notes : str
        Optional engineering notes to include in manifest.
    export_dir : str | Path
        Directory to place archive if `output_zip_path` not specified.

    Returns
    -------
    Path
        Absolute path to the created .zip archive.
    """
    exp_dir = Path(export_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_zip_path is None or isinstance(output_zip_path, bool):
        target_path = exp_dir / f"Run_Cell{cell_id}_{timestamp_str}.zip"
    else:
        target_path = Path(output_zip_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    files_manifest: List[Dict[str, Any]] = []
    archive_entries: Dict[str, bytes] = {}

    # 1. Test Recipe JSON
    if recipe is not None:
        try:
            rec_json = json.dumps(recipe.to_dict(), indent=2).encode("utf-8")
            archive_entries["recipe.json"] = rec_json
        except Exception as exc:
            logger.warning(f"Failed to serialize recipe: {exc}")

    # 2. Raw 10 Hz Telemetry CSV
    if raw_csv_path is not None:
        p_raw = Path(raw_csv_path)
        if p_raw.exists() and p_raw.stat().st_size > 0:
            try:
                raw_bytes = p_raw.read_bytes()
                archive_entries["telemetry_raw_10hz.csv"] = raw_bytes
            except Exception as exc:
                logger.warning(f"Could not read raw telemetry file {p_raw}: {exc}")

    # 3. Step Summary CSV
    if step_history:
        try:
            from io import StringIO
            # Generate temporary step summary
            import tempfile
            with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv", encoding="utf-8") as tmp:
                tmp_path = Path(tmp.name)
            write_step_summary_csv(tmp_path, step_history)
            step_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            archive_entries["summary_steps.csv"] = step_bytes
        except Exception as exc:
            logger.warning(f"Failed to generate step summary CSV: {exc}")

    # 4. Cycle Summary CSV
    if cycle_summaries:
        try:
            import tempfile
            with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv", encoding="utf-8") as tmp:
                tmp_path = Path(tmp.name)
            write_cycle_summary_csv(tmp_path, cycle_summaries)
            cycle_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            archive_entries["summary_cycles.csv"] = cycle_bytes
        except Exception as exc:
            logger.warning(f"Failed to generate cycle summary CSV: {exc}")

    # 5. Diagnostic Log Slice
    if app_log_path is None:
        app_log_path = DEFAULT_LOG_DIR / "cycler_app.txt"
    p_log = Path(app_log_path)
    if p_log.exists() and p_log.stat().st_size > 0:
        try:
            # Read last 5,000 lines (or full file if smaller than 5 MB)
            size = p_log.stat().st_size
            if size <= 5 * 1024 * 1024:
                log_bytes = p_log.read_bytes()
            else:
                with p_log.open("r", encoding="utf-8", errors="replace") as lf:
                    lines = lf.readlines()
                    tail_lines = lines[-5000:]
                    log_bytes = "".join(tail_lines).encode("utf-8")
            archive_entries["diagnostic_log.txt"] = log_bytes
        except Exception as exc:
            logger.warning(f"Failed to slice diagnostic log {p_log}: {exc}")

    # 6. Compute Cryptographic Hashes for manifest
    for fname, data in archive_entries.items():
        files_manifest.append({
            "filename": fname,
            "size_bytes": len(data),
            "sha256": compute_sha256(data),
        })

    # 7. Construct manifest.json
    manifest_data: Dict[str, Any] = {
        "format": "Bytehound-Run-Package",
        "version": "1.0.0",
        "exported_at": datetime.now().isoformat(),
        "cell_id": cell_id,
        "operator": operator,
        "test_status": test_status,
        "notes": notes,
        "recipe_name": recipe.recipe_name if recipe else "None",
        "cycles_completed": len(cycle_summaries) if cycle_summaries else 0,
        "steps_completed": len(step_history) if step_history else 0,
        "cumulative_metrics": {
            "charge_mah": round(metrics_tracker.cumulative_charge_mah, 2) if metrics_tracker else 0.0,
            "discharge_mah": round(metrics_tracker.cumulative_discharge_mah, 2) if metrics_tracker else 0.0,
            "charge_mwh": round(metrics_tracker.cumulative_charge_mwh, 2) if metrics_tracker else 0.0,
            "discharge_mwh": round(metrics_tracker.cumulative_discharge_mwh, 2) if metrics_tracker else 0.0,
        },
        "archive_files": files_manifest,
    }
    manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
    archive_entries["manifest.json"] = manifest_bytes

    # 8. Write ZIP archive
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc_name, arc_bytes in archive_entries.items():
            zf.writestr(arc_name, arc_bytes)

    logger.info(f"Successfully exported run package to {target_path} ({len(archive_entries)} files, {target_path.stat().st_size} bytes)")
    return target_path
