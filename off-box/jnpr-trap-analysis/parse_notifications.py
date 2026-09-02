#!/usr/bin/env python3
"""Library module: extract NOTIFICATION-TYPE definitions from a single Juniper
MIB text file. Used by build_full_catalog.py - not meant to be run directly."""
import re
from pathlib import Path

# Module name may be indented with tabs/spaces before "<NAME> DEFINITIONS ::= BEGIN"
MODULE_NAME_RE2 = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s+DEFINITIONS\b", re.MULTILINE)

# Matches: <name> NOTIFICATION-TYPE ... ::= { <parent> <num> }
NOTIF_RE = re.compile(
    r"^\s*([a-zA-Z][a-zA-Z0-9]*)\s+NOTIFICATION-TYPE\s*\n"
    r"(.*?)"
    r"::=\s*\{\s*([a-zA-Z][a-zA-Z0-9]*)\s+(\d+)\s*\}",
    re.MULTILINE | re.DOTALL,
)

OBJECTS_RE = re.compile(r"OBJECTS\s*\{(.*?)\}", re.DOTALL)
STATUS_RE = re.compile(r"STATUS\s+(\S+)")
DESCRIPTION_RE = re.compile(r'DESCRIPTION\s*"(.*?)"', re.DOTALL)

def clean_ws(s):
    return re.sub(r"\s+", " ", s).strip()

def get_module_name(text, fallback):
    m = MODULE_NAME_RE2.search(text)
    if m:
        return m.group(1)
    return fallback

def parse_file(path: Path):
    text = path.read_text(errors="replace")
    module = get_module_name(text, path.stem)
    results = []
    for m in NOTIF_RE.finditer(text):
        name, body, parent, num = m.groups()
        objects_m = OBJECTS_RE.search(body)
        objects = []
        if objects_m:
            raw = objects_m.group(1)
            # strip ASN.1 comments ( -- ... to end of line ) before splitting on commas
            raw = re.sub(r"--[^\n]*", "", raw)
            objects = [o.strip() for o in raw.split(",") if o.strip()]
        status_m = STATUS_RE.search(body)
        status = status_m.group(1) if status_m else ""
        desc_m = DESCRIPTION_RE.search(body)
        desc = clean_ws(desc_m.group(1)) if desc_m else ""
        is_juniper_enterprise = bool(re.match(r"^(JUNIPER|JNX)", module, re.IGNORECASE)) or name.startswith("jnx")
        results.append({
            "name": name,
            "module": module,
            "file": path.name,
            "oid_parent": parent,
            "oid_last": int(num),
            "status": status,
            "objects": objects,
            "description": desc,
            "juniper_enterprise": is_juniper_enterprise,
        })
    return results
