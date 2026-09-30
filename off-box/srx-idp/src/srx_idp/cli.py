from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from .delta import create_delta_report, download_signature_workbook
from .device import export_attack_list
from .download import build_update_url, download_update
from .manifest import changed_entries, pack_names, removed_entries


def add_platform_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", default="srxtvp")
    parser.add_argument("--os-version", default="22.4")
    parser.add_argument("--build", default="3")
    parser.add_argument("--detector", default="12.6.130180509")
    parser.add_argument("--release", default="10")
    parser.add_argument("--serial", default=os.environ.get("SRX_SERIAL"), help="device serial (default: $SRX_SERIAL)")


def pack_url(pack: object, args: argparse.Namespace) -> str:
    return build_update_url(
        str(pack), device=args.device, os_version=args.os_version, build=args.build,
        detector=args.detector, release=args.release, serial=args.serial,
    )


def find_retired(args: argparse.Namespace) -> tuple[list[str], set[str]]:
    """Retired signatures and the target pack's signature names, from local files or fresh downloads."""
    if args.old_pack and args.new_pack:
        return removed_entries(args.old_pack, args.new_pack), pack_names(args.new_pack)
    with tempfile.TemporaryDirectory() as tmp:
        print("Checking retired signatures: downloading two update packs (about 60 MB each)...")
        old = args.old_pack or download_update(pack_url(args.active_pack, args), Path(tmp), "old")
        new = args.new_pack or download_update(pack_url(args.target_pack or "latest", args), Path(tmp), "new")
        return removed_entries(old, new), pack_names(new)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Juniper SRX IDP utilities")
    commands = parser.add_subparsers(dest="command", required=True)

    spreadsheet = commands.add_parser("spreadsheet", help="create a signature delta report")
    spreadsheet.add_argument("active_pack", type=int)
    spreadsheet.add_argument("--input", type=Path)
    spreadsheet.add_argument("--output-dir", type=Path, default=Path.cwd())
    spreadsheet.add_argument("--target-pack", type=int, help="cap the delta at this pack (default: newest available)")
    spreadsheet.add_argument("--check-retired", action="store_true", help="also list signatures retired between the packs")
    spreadsheet.add_argument("--old-pack", type=Path, help="local update pack for the active version (with --check-retired)")
    spreadsheet.add_argument("--new-pack", type=Path, help="local update pack for the target version (with --check-retired)")
    add_platform_options(spreadsheet)

    manifest = commands.add_parser("manifest", help="compare two SignatureUpdate XML files")
    manifest.add_argument("old", type=Path)
    manifest.add_argument("new", type=Path)

    download = commands.add_parser("download", help="download SignatureUpdate packs from Juniper")
    download.add_argument("packs", nargs="*", default=["latest"], help='pack numbers or "latest" (default: latest)')
    download.add_argument("--output-dir", type=Path, default=Path.cwd())
    download.add_argument("--keep-archive", action="store_true", help="keep the downloaded .tgz")
    add_platform_options(download)

    device = commands.add_parser("device-attacks", help="export attacks from an SRX")
    device.add_argument("--output-dir", type=Path, default=Path.cwd())
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "spreadsheet":
        if (args.old_pack or args.new_pack) and not args.check_retired:
            build_parser().error("--old-pack/--new-pack require --check-retired")
        source = args.input or download_signature_workbook(args.output_dir / "signature.xlsx")
        retired, names = find_retired(args) if args.check_retired else (None, None)
        try:
            report, workbook, count = create_delta_report(
                source, args.active_pack, args.output_dir, target_pack=args.target_pack, retired=retired, pack_names=names
            )
        except ValueError as error:
            build_parser().error(str(error))
        print(f"Created {report} and {workbook} with {count} signatures")
    elif args.command == "manifest":
        changes = changed_entries(args.old, args.new)
        print("\n".join(changes))
        print(f"Changed or added entries: {len(changes)}")
    elif args.command == "download":
        for pack in args.packs:
            url = pack_url(pack, args)
            print(f"Downloading {pack} from Juniper. This may take a moment...")
            print(f"Created {download_update(url, args.output_dir, f'offline-update-{pack}', keep_archive=args.keep_archive)}")
    elif args.command == "device-attacks":
        print(f"Created {export_attack_list(args.output_dir)}")


if __name__ == "__main__":
    main()

