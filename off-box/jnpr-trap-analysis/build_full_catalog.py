#!/usr/bin/env python3
"""Unified Junos + Junos-EVO trap catalog builder.

Run this from anywhere - it locates everything relative to its own location:
    python3 build_full_catalog.py [--include-standard]

To add a new MIB release: drop the extracted directory into this same folder
(next to this script) and re-run. It is picked up automatically if its name
matches one of the two conventions already in use here:

  - Junos (nested):   juniper-mibs-<version>/        containing JuniperMibs/
                       and StandardMibs/ subdirectories.
                       e.g. juniper-mibs-27.1R1

  - Junos-EVO (flat):  junos-evo-mibs.<version>/      all .txt files directly
                       inside, no subdirectories.
                       e.g. junos-evo-mibs.27.1R1-EVO

  Version = whatever follows the "juniper-mibs-" or "junos-evo-mibs." prefix
  in the directory name - that's exactly the label shown in the catalog, so
  name the directory the way you want the release to read.

If you're adding a directory that doesn't fit either pattern (a third OS, a
one-off naming scheme), add an explicit entry to MANUAL_RELEASES below
instead of renaming it: (os_label, version_label, "nested"|"flat", path).

Scans every loaded release for NOTIFICATION-TYPE definitions, resolves each
varbind's enumerated values via the full OBJECT-TYPE/TEXTUAL-CONVENTION index,
and builds one registry keyed by trap name with a presence/snapshot per
release, tagged with OS (Junos vs Junos-EVO).

--include-standard / --enterprise-only (default) controls whether files that
aren't Juniper-authored (no jnx- prefix) are scanned for NOTIFICATION-TYPE
definitions at all. The object/TC index used to resolve varbind enums always
scans every file regardless, since Juniper's own objects frequently reference
standard textual conventions (TruthValue, InetAddressType, RowStatus, ...).

Requires: pip3 install openpyxl
"""
import sys
import re
import json
import argparse
from pathlib import Path
from collections import Counter

SNMP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SNMP_ROOT))
import parse_notifications as PN   # noqa: E402
import parse_objects as PO         # noqa: E402

# Manual overrides/additions - for a directory that doesn't match either
# auto-discovery naming pattern below. Same tuple shape as what discover_releases()
# produces: (os_label, version_label, "nested"|"flat", path).
MANUAL_RELEASES = [
    # ("Junos", "27.1R1", "nested", SNMP_ROOT / "some-oddly-named-dir"),
]

JUNOS_DIR_RE = re.compile(r"^juniper-mibs-(.+)$")
EVO_DIR_RE = re.compile(r"^junos-evo-mibs\.(.+)$")

def discover_releases(root: Path):
    """Find every juniper-mibs-* (nested) and junos-evo-mibs.* (flat) directory
    next to this script, in name order (which sorts chronologically for
    Juniper's YY.MRn version scheme)."""
    found = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        m = JUNOS_DIR_RE.match(d.name)
        if m and (d / "JuniperMibs").is_dir() and (d / "StandardMibs").is_dir():
            found.append(("Junos", m.group(1), "nested", d))
            continue
        m = EVO_DIR_RE.match(d.name)
        if m and any(d.glob("*.txt")):
            found.append(("Junos-EVO", m.group(1), "flat", d))
            continue
    return found

RELEASES = discover_releases(SNMP_ROOT) + MANUAL_RELEASES

JNX_FILE_RE = re.compile(r"^(mib-)?jnx-", re.IGNORECASE)

def is_juniper_file(path: Path) -> bool:
    return bool(JNX_FILE_RE.match(path.name))

CATEGORY_RULES = [
    ("chassis-hardware", re.compile(r"chassis|fru\b|power-supply|fan\b|alarm|fabric|redundancy|hostresources", re.I), "Chassis & hardware"),
    ("routing", re.compile(r"ospf|bgp|mpls|ldp|rsvp|mldp|vpls|isis|vpn|mvpn|l2l3vpn|mimstp|pim|msdp|pcep|l3vpn", re.I), "Routing & switching protocols"),
    ("mobile-core", re.compile(r"mobile-gateway|mbg-smi|ggsn", re.I), "Mobile gateway & core"),
    ("security", re.compile(r"ipsec|secintel|screening|idp|aamw|nat|js-|user-aaa|auth|gdoi|securewire|lsys", re.I), "Security & policy"),
    ("timing", re.compile(r"timing", re.I), "Timing & synchronization"),
    ("interfaces-optics", re.compile(r"ifotn|optics|dom\b|sonet|atm|if-extensions|if-capability|ifmib|dcu|ethernet|8021|802\.1|802\.3|lldp", re.I), "Interfaces & optics"),
    ("ha", re.compile(r"jsrpd|-red\b", re.I), "High availability"),
    ("monitoring-probes", re.compile(r"ping|rpm|tlb|coll\b|soam|rmon", re.I), "Monitoring & probes"),
    ("platform-system", re.compile(r"cfgmgmt|license|syslog|cos\b|dfc|pfe|jvae|util|event", re.I), "Platform & system"),
]
CATEGORY_LABELS = {"other": "Other"}
for k, _, lbl in CATEGORY_RULES:
    CATEGORY_LABELS[k] = lbl

def categorize(filename):
    for key, rx, _ in CATEGORY_RULES:
        if rx.search(filename):
            return key
    return "other"


def files_for_release(kind, root: Path):
    if kind == "nested":
        juniper_files = sorted((root / "JuniperMibs").glob("*.txt"))
        standard_files = sorted((root / "StandardMibs").glob("*.txt"))
    else:
        all_files = sorted(root.glob("*.txt"))
        juniper_files = [f for f in all_files if is_juniper_file(f)]
        standard_files = [f for f in all_files if not is_juniper_file(f)]
    return juniper_files, standard_files


def parse_release(kind, root: Path, include_standard: bool):
    juniper_files, standard_files = files_for_release(kind, root)
    notif_files = juniper_files + (standard_files if include_standard else [])
    object_files = juniper_files + standard_files  # always full breadth for enum resolution

    all_notifs = []
    for f in notif_files:
        try:
            all_notifs.extend(PN.parse_file(f))
        except Exception as e:
            print(f"  ERROR parsing notifications in {f}: {e}")

    all_tcs, all_objs = {}, {}
    for f in object_files:
        try:
            _, tcs, objs = PO.parse_file(f)
        except Exception as e:
            print(f"  ERROR parsing objects in {f}: {e}")
            continue
        for k, v in tcs.items():
            all_tcs.setdefault(k, v)
        for k, v in objs.items():
            all_objs.setdefault(k, v)

    for name, o in all_objs.items():
        if o["enum"] is not None:
            continue
        base = o["base"]
        seen = set()
        while base in all_tcs and base not in seen:
            seen.add(base)
            tc = all_tcs[base]
            if tc["enum"] is not None:
                o["enum"] = tc["enum"]
                break
            base = tc["base"]

    by_name = {}
    for n in all_notifs:
        detail = []
        for obj_name in n["objects"]:
            o = all_objs.get(obj_name)
            detail.append({"name": obj_name, "base": o["base"] if o else None, "enum": o["enum"] if o else None})
        snapshot = {
            "module": n["module"],
            "file": n["file"],
            "oid": f'{n["oid_parent"]}.{n["oid_last"]}',
            "status": n["status"],
            "description": n["description"],
            "objects_detail": detail,
            "juniper_enterprise": n["juniper_enterprise"],
        }
        by_name.setdefault(n["name"], snapshot)

    return by_name


def varbinds_text(objects_detail):
    parts = []
    for od in objects_detail:
        if od.get("enum"):
            vals = ", ".join(f"{k}={v}" for k, v in sorted(od["enum"].items(), key=lambda kv: int(kv[0])))
            parts.append(f"{od['name']} [{od['base']}]: {vals}")
        else:
            parts.append(od["name"] + (f" [{od['base']}]" if od.get("base") else ""))
    return " | ".join(parts)


def lifecycle_for(version_labels, present_labels):
    idxs = [version_labels.index(l) for l in present_labels]
    if len(present_labels) == len(version_labels):
        return "Present in all versions"
    if not present_labels:
        return "Unknown"
    first_present = version_labels[min(idxs)]
    last_present = version_labels[max(idxs)]
    contiguous = idxs == list(range(min(idxs), max(idxs) + 1))
    if min(idxs) == 0 and contiguous and max(idxs) < len(version_labels) - 1:
        return f"Removed after {last_present}"
    if max(idxs) == len(version_labels) - 1 and contiguous:
        return f"Added in {first_present}"
    if contiguous:
        return f"Present {first_present}–{last_present} only"
    return f"Present in {', '.join(present_labels)} (non-contiguous)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-standard", action="store_true",
                     help="Also scan non-Juniper-authored MIB files for NOTIFICATION-TYPE definitions "
                          "(adds standards-track traps like real BGP4-MIB, OSPF, PIM, RMON, etc). "
                          "Default: Juniper-enterprise files only.")
    args = ap.parse_args()
    include_standard = args.include_standard

    if not RELEASES:
        print(f"No MIB release directories found next to {__file__}.")
        print("Expected juniper-mibs-<version>/ (with JuniperMibs/+StandardMibs/ subdirs)")
        print("or junos-evo-mibs.<version>/ (flat, all .txt files directly inside).")
        sys.exit(1)

    print(f"Mode: {'including standards-track files' if include_standard else 'Juniper-authored files only (enterprise scope)'}")
    print(f"Discovered {len(RELEASES)} release(s):")
    for os_label, version_label, kind, root in RELEASES:
        print(f"  {os_label:10s} {version_label:20s} ({kind}, {root.name})")
    print()

    release_keys = []  # (os, version) in load order
    per_release = {}
    for os_label, version_label, kind, root in RELEASES:
        print(f"Parsing {os_label} {version_label} ({root.name}) ...")
        by_name = parse_release(kind, root, include_standard)
        per_release[(os_label, version_label)] = by_name
        release_keys.append((os_label, version_label))
        print(f"  {len(by_name)} unique notification names")

    junos_versions = [v for o, v in release_keys if o == "Junos"]
    evo_versions = [v for o, v in release_keys if o == "Junos-EVO"]
    release_labels = [f"{o} {v}" for o, v in release_keys]  # display / dropdown labels

    all_names = set()
    for by_name in per_release.values():
        all_names.update(by_name.keys())
    print(f"\nUnion across all {len(release_keys)} releases: {len(all_names)} unique notification names")

    registry = []
    for name in sorted(all_names):
        versions = {}
        present_junos, present_evo = [], []
        for os_label, version_label in release_keys:
            snap = per_release[(os_label, version_label)].get(name)
            label = f"{os_label} {version_label}"
            if snap:
                versions[label] = {"present": True, **snap}
                (present_junos if os_label == "Junos" else present_evo).append(version_label)
            else:
                versions[label] = {"present": False}

        rep = None
        for os_label, version_label in reversed(release_keys):
            label = f"{os_label} {version_label}"
            if versions[label]["present"]:
                rep = versions[label]
                break

        if present_junos and present_evo:
            os_scope = "Both"
        elif present_junos:
            os_scope = "Junos only"
        elif present_evo:
            os_scope = "Junos-EVO only"
        else:
            os_scope = "Unknown"

        registry.append({
            "name": name,
            "module": rep["module"] if rep else "",
            "category": categorize(rep["file"] if rep else ""),
            "juniper_enterprise": rep["juniper_enterprise"] if rep else False,
            "os_scope": os_scope,
            "lifecycle_junos": lifecycle_for(junos_versions, present_junos) if junos_versions else "n/a",
            "lifecycle_evo": lifecycle_for(evo_versions, present_evo) if evo_versions else "n/a",
            "present_junos": present_junos,
            "present_evo": present_evo,
            "versions": versions,
        })

    out_json = SNMP_ROOT / "juniper_notifications_full.json"
    out_json.write_text(json.dumps({
        "release_labels": release_labels,
        "junos_versions": junos_versions,
        "evo_versions": evo_versions,
        "include_standard": include_standard,
        "registry": registry,
    }, indent=2))
    print(f"\nWrote {out_json} ({out_json.stat().st_size / 1024:.0f} KB)")

    scope_counts = Counter(r["os_scope"] for r in registry)
    print("\nOS scope breakdown (union across all loaded versions of each OS):")
    for k, v in scope_counts.most_common():
        print(f"  {v:4d}  {k}")

    ent_counts = Counter(r["juniper_enterprise"] for r in registry)
    print(f"\nJuniper-enterprise: {ent_counts.get(True, 0)}   Standards-track: {ent_counts.get(False, 0)}")

    build_xlsx(release_labels, junos_versions, evo_versions, registry, include_standard)


def build_xlsx(release_labels, junos_versions, evo_versions, registry, include_standard):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog"

    headers = ["Name", "Module", "Category", "Juniper enterprise", "OS scope",
               "Junos lifecycle", "Junos-EVO lifecycle"]
    headers += [f"In {label}" for label in release_labels]
    headers += ["OID differs (Junos vs EVO)?", "Description differs (Junos vs EVO)?", "Varbinds differ (Junos vs EVO)?"]
    headers += ["OID (latest Junos)", "OID (latest Junos-EVO)"]
    headers += ["Description (latest Junos)", "Description (latest Junos-EVO)"]
    headers += ["Varbinds (latest Junos)", "Varbinds (latest Junos-EVO)"]
    headers += ["Status (latest)", "Source file (latest)"]

    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="0E6E82")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    scope_fill = {
        "Both": PatternFill("solid", fgColor="DCEEF1"),
        "Junos only": PatternFill("solid", fgColor="FDECC8"),
        "Junos-EVO only": PatternFill("solid", fgColor="ECE5F7"),
    }
    changed_fill = PatternFill("solid", fgColor="FBE1E1")

    def latest_present(labels, versions):
        for label in reversed(labels):
            v = versions.get(label)
            if v and v["present"]:
                return v
        return None

    for r in registry:
        junos_labels = [f"Junos {v}" for v in junos_versions]
        evo_labels = [f"Junos-EVO {v}" for v in evo_versions]
        latest_j = latest_present(junos_labels, r["versions"])
        latest_e = latest_present(evo_labels, r["versions"])

        oid_j = latest_j["oid"] if latest_j else ""
        oid_e = latest_e["oid"] if latest_e else ""
        desc_j = latest_j["description"] if latest_j else ""
        desc_e = latest_e["description"] if latest_e else ""
        vb_j = varbinds_text(latest_j["objects_detail"]) if latest_j else ""
        vb_e = varbinds_text(latest_e["objects_detail"]) if latest_e else ""

        oid_differs = bool(latest_j and latest_e and oid_j != oid_e)
        desc_differs = bool(latest_j and latest_e and desc_j != desc_e)
        vb_differs = bool(latest_j and latest_e and vb_j != vb_e)

        rep = latest_e or latest_j

        row = [r["name"], r["module"], CATEGORY_LABELS.get(r["category"], r["category"]),
               "Yes" if r["juniper_enterprise"] else "No", r["os_scope"],
               r["lifecycle_junos"], r["lifecycle_evo"]]
        for label in release_labels:
            row.append("Yes" if r["versions"][label]["present"] else "No")
        row += ["Yes" if oid_differs else ("N/A" if not (latest_j and latest_e) else "No"),
                "Yes" if desc_differs else ("N/A" if not (latest_j and latest_e) else "No"),
                "Yes" if vb_differs else ("N/A" if not (latest_j and latest_e) else "No")]
        row += [oid_j, oid_e, desc_j, desc_e, vb_j, vb_e]
        row += [rep.get("status", "") if rep else "", rep.get("file", "") if rep else ""]
        ws.append(row)

    n_rows = len(registry) + 1
    n_cols = len(headers)
    scope_col = 5
    for i in range(2, n_rows + 1):
        scope_val = ws.cell(row=i, column=scope_col).value
        if scope_val in scope_fill:
            ws.cell(row=i, column=scope_col).fill = scope_fill[scope_val]
        for col_name in ["OID differs (Junos vs EVO)?", "Description differs (Junos vs EVO)?", "Varbinds differ (Junos vs EVO)?"]:
            c = headers.index(col_name) + 1
            if ws.cell(row=i, column=c).value == "Yes":
                ws.cell(row=i, column=c).fill = changed_fill

    widths = {"Name": 34, "Module": 26, "Category": 24, "Juniper enterprise": 12, "OS scope": 16,
              "Junos lifecycle": 22, "Junos-EVO lifecycle": 22,
              "OID differs (Junos vs EVO)?": 14, "Description differs (Junos vs EVO)?": 16, "Varbinds differ (Junos vs EVO)?": 14,
              "OID (latest Junos)": 22, "OID (latest Junos-EVO)": 22,
              "Description (latest Junos)": 55, "Description (latest Junos-EVO)": 55,
              "Varbinds (latest Junos)": 45, "Varbinds (latest Junos-EVO)": 45,
              "Status (latest)": 12, "Source file (latest)": 26}
    for label in release_labels:
        widths[f"In {label}"] = 12
    for idx, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = widths.get(h, 16)
    ws.freeze_panes = "H2"
    ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{n_rows}"

    # ---------- Summary ----------
    ws2 = wb.create_sheet("Summary")
    ws2["A1"] = "Juniper trap catalog — Junos vs Junos-EVO summary"
    ws2["A1"].font = Font(bold=True, size=14)
    ws2["A2"] = "Scope: " + ("Juniper-enterprise + standards-track" if include_standard else "Juniper-enterprise files only")
    ws2.append([])
    ws2.append(["Release", "Total notifications", "Juniper-enterprise", "Standards-track"])
    hdr_row = ws2.max_row
    for c in range(1, 5):
        ws2.cell(row=hdr_row, column=c).font = Font(bold=True)
    for label in release_labels:
        total = sum(1 for r in registry if r["versions"][label]["present"])
        ent = sum(1 for r in registry if r["versions"][label]["present"] and r["versions"][label].get("juniper_enterprise"))
        ws2.append([label, total, ent, total - ent])

    ws2.append([])
    ws2.append(["OS overlap (union across all loaded versions of each OS)"])
    ws2.cell(row=ws2.max_row, column=1).font = Font(bold=True)
    ws2.append(["Scope", "Count"])
    hdr_row2 = ws2.max_row
    for c in (1, 2):
        ws2.cell(row=hdr_row2, column=c).font = Font(bold=True)
    scope_counts = Counter(r["os_scope"] for r in registry)
    for k in ["Both", "Junos only", "Junos-EVO only"]:
        ws2.append([k, scope_counts.get(k, 0)])

    ws2.append([])
    ws2.append(["Version-over-version deltas within each OS"])
    ws2.cell(row=ws2.max_row, column=1).font = Font(bold=True)
    ws2.append(["From → To", "Added", "Removed", "Changed", "Unchanged"])
    hdr_row3 = ws2.max_row
    for c in range(1, 6):
        ws2.cell(row=hdr_row3, column=c).font = Font(bold=True)

    def diff_counts(a_label, b_label):
        added = removed = changed = unchanged = 0
        for r in registry:
            va, vb = r["versions"][a_label], r["versions"][b_label]
            if va["present"] and vb["present"]:
                differs = (va.get("oid") != vb.get("oid")) or (va.get("description") != vb.get("description")) or \
                          (varbinds_text(va.get("objects_detail", [])) != varbinds_text(vb.get("objects_detail", [])))
                changed += 1 if differs else 0
                unchanged += 0 if differs else 1
            elif vb["present"] and not va["present"]:
                added += 1
            elif va["present"] and not vb["present"]:
                removed += 1
        return added, removed, changed, unchanged

    for labels, os_name in [([f"Junos {v}" for v in junos_versions], "Junos"), ([f"Junos-EVO {v}" for v in evo_versions], "Junos-EVO")]:
        for i in range(len(labels) - 1):
            a, b = labels[i], labels[i + 1]
            added, removed, changed, unchanged = diff_counts(a, b)
            ws2.append([f"{a} → {b}", added, removed, changed, unchanged])

    for col, w in zip("ABCDE", [32, 16, 16, 12, 14]):
        ws2.column_dimensions[col].width = w

    # ---------- Legend ----------
    ws3 = wb.create_sheet("Legend")
    ws3["A1"] = "How to read this workbook"
    ws3["A1"].font = Font(bold=True, size=14)
    legend_lines = [
        "",
        f"Scope: {'Juniper-authored + standards-track MIB files' if include_standard else 'Juniper-authored MIB files only (jnx-*)'}.",
        "  Re-run build_full_catalog.py with/without --include-standard to change this.",
        "",
        "Catalog sheet: one row per unique SNMP notification (trap) name, unioned across every Junos and Junos-EVO release loaded.",
        "'OS scope': Both = defined on both operating systems. Junos only / Junos-EVO only = defined on just one.",
        "'Junos lifecycle' / 'Junos-EVO lifecycle': Added in X / Removed after X / Present in all versions — computed within that OS's own version history only.",
        "'In <release>' columns: Yes/No presence per individual loaded release.",
        "'OID / Description / Varbinds differs (Junos vs EVO)?': compares the latest loaded release of each OS. N/A if the trap isn't present on both.",
        "  This is the fastest way to spot traps that exist on both OSes but are defined differently — different OID, wording, or varbind values.",
        "'Varbinds' columns list each carried object as name [base type]: value=label, value=label, … for objects with an enumerated SYNTAX.",
        "",
        "Source: NOTIFICATION-TYPE definitions are what a device actually sends as an SNMP trap/inform.",
        "Varbind value decoding comes from each object's own OBJECT-TYPE SYNTAX (inline INTEGER/BITS enum, or via an imported TEXTUAL-CONVENTION) —",
        "  this resolution always uses the full MIB set regardless of the --include-standard scope, since Juniper's own objects often reference standard conventions.",
    ]
    for i, line in enumerate(legend_lines, start=2):
        ws3.cell(row=i, column=1, value=line)
    ws3.column_dimensions["A"].width = 135

    out_xlsx = SNMP_ROOT / "juniper_trap_catalog.xlsx"
    wb.save(out_xlsx)
    print(f"Wrote {out_xlsx}")


if __name__ == "__main__":
    main()
