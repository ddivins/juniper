from __future__ import annotations

import gzip
import shutil
from pathlib import Path
from urllib.parse import urlencode

import requests


UPDATE_URL = "https://signatures.juniper.net/cgi-bin/index.cgi"


def build_update_url(
    target: str,
    *,
    device: str = "srxtvp",
    os_version: str = "22.4",
    build: str = "3",
    detector: str = "12.6.130180509",
    release: str = "10",
    serial: str | None = None,
) -> str:
    """URL for a full IDP signature update pack; ``target`` is "latest" or a pack number."""
    params = {
        "device": device,
        "adv_dev_info": "",
        "feature": "idp",
        "os": os_version,
        "build": build,
        "dfa": "hs",
        "platform_version": "",
        "detector": detector,
        "from": "",
        "to": target,
        "type": "update",
    }
    if serial:
        params["sn"] = serial
    params["release"] = release
    return f"{UPDATE_URL}?{urlencode(params)}"


def gunzip_file(source: Path, destination: Path) -> Path:
    with gzip.open(source, "rb") as f_in, destination.open("wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return destination


def download_update(url: str, output_dir: Path, name: str, timeout: int = 300, keep_archive: bool = False) -> Path:
    """Download an update pack to ``output_dir/<name>.tgz`` and decompress it to ``output_dir/<name>``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{name}.tgz"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    archive.write_bytes(response.content)
    extracted = gunzip_file(archive, output_dir / name)
    if not keep_archive:
        archive.unlink()
    return extracted
