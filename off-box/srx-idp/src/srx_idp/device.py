from __future__ import annotations

import os
from pathlib import Path

from jnpr.junos import Device


def connection_parameters() -> dict[str, object]:
    host = os.environ.get("SRX_HOSTNAME")
    user = os.environ.get("SRX_USERNAME")
    if not host or not user:
        raise ValueError("SRX_HOSTNAME and SRX_USERNAME are required")
    params: dict[str, object] = {
        "host": host,
        "port": int(os.environ.get("SRX_PORT", "22")),
        "user": user,
        "gather_facts": False,
    }
    key = os.environ.get("SRX_SSH_KEY")
    password = os.environ.get("SRX_PASSWORD")
    if key:
        params["ssh_private_key_file"] = str(Path(key).expanduser())
    elif password:
        params["password"] = password
    else:
        raise ValueError("SRX_SSH_KEY or SRX_PASSWORD is required")
    return params


def export_attack_list(output_dir: Path) -> Path:
    with Device(**connection_parameters()) as device:
        device.timeout = 300
        version_xml = device.rpc.get_idp_security_package_information()
        versions = version_xml.xpath("//security-package-version/text()")
        version = versions[0].split("(", 1)[0].strip() if versions else "unknown"
        response = device.rpc.get_idp_group_attacklist_information(
            predefined_group="All Attacks", recursive=True
        )
        attacks = sorted(set(response.xpath("//idp-group-attack-list-entry/text()")))
    destination = output_dir / f"idp_attack_list_{version}.txt"
    destination.write_text("\n".join(attacks) + "\n", encoding="utf-8")
    return destination

