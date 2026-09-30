"""Create an SRX IDP signature delta report.

Compatibility entry point retained from the original SRX_IDP project.

Usage:
    python srx_idp_signature_delta_xls.py <current_idp_sig_pack> [offline]
"""

from __future__ import annotations

import sys
from pathlib import Path

from srx_idp.delta import create_delta_report, download_signature_workbook


USAGE = "Usage: srx_idp_signature_delta_xls.py <current_idp_sig_pack> offline<optional>"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) not in {1, 2} or (len(arguments) == 2 and arguments[1] != "offline"):
        print(USAGE)
        return 1

    try:
        active_pack = int(arguments[0])
    except ValueError:
        print("Argument must be an integer")
        print(USAGE)
        return 1

    output_dir = Path.cwd()
    signature_file = output_dir / "signature.xlsx"
    if len(arguments) == 2:
        if not signature_file.is_file():
            print(f"Offline mode requires {signature_file}")
            return 1
        print(f"Using offline {signature_file.name}")
    else:
        print("Downloading latest signature.xlsx from Juniper. This may take a minute...")
        download_signature_workbook(signature_file)

    report, workbook, count = create_delta_report(signature_file, active_pack, output_dir)
    print(f"Since Active SigPack {active_pack} there are {count} new signatures")
    print(f"Please see {workbook.name} for the full delta report")
    print(f"Please see {report.name} for signature deltas and Junos commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

