from __future__ import annotations

from pathlib import Path
from typing import Iterable
import warnings

import openpyxl
import requests


SIGNATURE_URL = "https://apigw.juniper.net/signature-web/api/signature/download/ips?format=xls"
REQUIRED_COLUMNS = {
    "signature_update_number",
    "signature_name",
    "signature_severity",
    "signature_release_date",
}


def download_signature_workbook(destination: Path, timeout: int = 120) -> Path:
    response = requests.get(SIGNATURE_URL, timeout=timeout)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def select_delta_rows(
    rows: Iterable[dict[str, object]], active_pack: int, target_pack: int | None = None
) -> list[dict[str, object]]:
    """Rows newer than ``active_pack`` and, when given, no newer than ``target_pack``."""
    selected = []
    for row in rows:
        update = row.get("signature_update_number")
        if update is None:
            continue
        number = int(update)
        if number > active_pack and (target_pack is None or number <= target_pack):
            selected.append(row)
    return sorted(selected, key=lambda row: int(row["signature_update_number"]))


def load_rows(source: Path) -> tuple[list[str], list[dict[str, object]]]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Workbook contains no default style, apply openpyxl's default",
            category=UserWarning,
            module="openpyxl.styles.stylesheet",
        )
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook["signatures"]
        headers = [str(cell.value) if cell.value is not None else "" for cell in sheet[1]]
        missing = REQUIRED_COLUMNS.difference(headers)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        rows = [dict(zip(headers, values)) for values in sheet.iter_rows(min_row=2, values_only=True)]
        return headers, rows
    finally:
        workbook.close()


def write_delta_workbook(destination: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "signatures"
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header) for header in headers])
    workbook.save(destination)


def build_junos_commands(signature_names: Iterable[str]) -> list[str]:
    prefix = "set security idp custom-attack-group SIG_DELTA group-members"
    commands = ["delete security idp custom-attack-group SIG_DELTA"]
    commands.append(f"{prefix} SCAN:MISC:IDP-TEST")
    commands.extend(f"{prefix} {name}" for name in sorted(set(signature_names)))
    return commands


def create_delta_report(
    source: Path,
    active_pack: int,
    output_dir: Path,
    target_pack: int | None = None,
    retired: list[str] | None = None,
    pack_names: set[str] | None = None,
) -> tuple[Path, Path, int]:
    """Write the delta report and workbook.

    ``target_pack`` caps the delta at a pack you are installing instead of the newest in the
    spreadsheet. ``retired`` is the list of signatures removed between the two packs; ``None``
    means retirements were not checked, which the report states explicitly. ``pack_names`` is the
    set of signature names in the target pack; delta signatures missing from it are left out of
    the commands (they would not commit on a device running that pack) and listed separately.
    """
    headers, rows = load_rows(source)
    newest = max((int(row["signature_update_number"]) for row in rows if row.get("signature_update_number") is not None), default=active_pack)
    if target_pack is not None:
        if target_pack <= active_pack:
            raise ValueError(f"target pack {target_pack} must be greater than active pack {active_pack}")
        if target_pack > newest:
            raise ValueError(f"target pack {target_pack} is newer than the newest pack in the spreadsheet ({newest})")
    latest_pack = target_pack if target_pack is not None else newest
    delta_rows = select_delta_rows(rows, active_pack, target_pack)
    excluded: list[str] = []
    if pack_names is not None:
        excluded = sorted({str(r["signature_name"]) for r in delta_rows if r.get("signature_name") and str(r["signature_name"]) not in pack_names})
        delta_rows = [r for r in delta_rows if str(r.get("signature_name")) in pack_names]
    report_path = output_dir / f"sig_delta_report_{active_pack}_{latest_pack}.txt"
    workbook_path = output_dir / f"signature_delta_{active_pack}_{latest_pack}.xlsx"
    names = [str(row["signature_name"]) for row in delta_rows if row.get("signature_name")]
    lines = [
        f"Since active signature pack {active_pack} there are {len(names)} new signatures",
        f"{'Target' if target_pack is not None else 'Newest'} signature pack is {latest_pack}",
        "",
        *build_junos_commands(names),
        "",
        *retired_section(retired, active_pack, latest_pack),
        *excluded_section(excluded, pack_names is not None),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_delta_workbook(workbook_path, headers, delta_rows)
    return report_path, workbook_path, len(names)


def retired_section(retired: list[str] | None, active_pack: int, latest_pack: int) -> list[str]:
    """Report lines listing retired signatures. Prefixed with '#' so the file can be pasted into Junos."""
    if retired is None:
        return ["# Retired signatures: not checked (run with --check-retired)"]
    lines = [f"# Retired signatures between pack {active_pack} and {latest_pack}: {len(retired)}"]
    if retired:
        lines.append("# Present in the older pack, absent from the newer. Remove any references to them from your config.")
        lines.extend(f"# {name}" for name in retired)
    return lines


def excluded_section(excluded: list[str], checked: bool) -> list[str]:
    """Delta signatures left out because the target pack does not contain them."""
    if not checked or not excluded:
        return []
    return [
        "",
        f"# Excluded from SIG_DELTA ({len(excluded)}): in the spreadsheet but not in the target pack, so they cannot be added on a device running it",
        *(f"# {name}" for name in excluded),
    ]
