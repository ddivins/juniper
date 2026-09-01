#!/usr/bin/env python3

from jnpr.junos import Device
from jnpr.junos.exception import RpcError, ConnectError
import re
import sys

MACRO_NAME = "CLEAR-SESSIONS-PREFIXES"
DEBUG = False

# Used only if the apply-macro isn't configured at all (see README).
# Deliberately empty: with no macro configured, the script should clear
# nothing rather than guess.
DEFAULT_ENTRIES = []

# Data-name format: <direction>-<family>-<n>
ENTRY_NAME_RE = re.compile(r"^(src|dst|both)-(inet6?)-(\d+)$")

def debug_print(msg):
    if DEBUG:
        print(f"DEBUG: {msg}")

def parse_apply_macro_entries(xml_root, source_name):
    entries = []

    macros = xml_root.xpath(
        ".//*[local-name()='apply-macro'][*[local-name()='name' and text()='{}']]".format(MACRO_NAME)
    )

    debug_print(f"{source_name}: found {len(macros)} apply-macro entries named {MACRO_NAME}")

    for macro in macros:
        data_nodes = macro.xpath("./*[local-name()='data']")
        debug_print(f"{source_name}: found {len(data_nodes)} data nodes under {MACRO_NAME}")

        for data in data_nodes:
            name_nodes = data.xpath("./*[local-name()='name']/text()")
            value_nodes = data.xpath("./*[local-name()='value']/text()")

            if not name_nodes or not value_nodes:
                continue

            name = name_nodes[0].strip()
            value = value_nodes[0].strip()

            debug_print(f"{source_name}: macro data {name} = {value}")

            if not value:
                continue

            match = ENTRY_NAME_RE.match(name)
            if not match:
                debug_print(f"{source_name}: skipping {name} -- doesn't match <src|dst|both>-<inet|inet6>-<n>")
                continue

            direction, family, index = match.groups()
            entries.append((int(index), direction, family, value))

    entries.sort(key=lambda e: e[0])

    return [
        {"direction": direction, "family": family, "prefix": prefix}
        for _, direction, family, prefix in entries
    ]

def get_entries_from_apply_macro(dev):
    try:
        rsp = dev.rpc.cli(
            command=f"show configuration apply-macro {MACRO_NAME}",
            format="xml"
        )

        entries = parse_apply_macro_entries(
            rsp,
            "cli show configuration apply-macro"
        )

        if entries:
            debug_print(f"using entries from apply-macro: {entries}")
            return entries

    except Exception as err:
        debug_print(f"cli show configuration apply-macro failed: {err}")

    try:
        cfg = dev.rpc.get_config(
            options={"database": "committed"}
        )

        entries = parse_apply_macro_entries(
            cfg,
            "get_config committed"
        )

        if entries:
            debug_print(f"using entries from committed config: {entries}")
            return entries

    except Exception as err:
        debug_print(f"get_config committed failed: {err}")

    debug_print(f"no apply-macro entries found; falling back to defaults {DEFAULT_ENTRIES}")

    return DEFAULT_ENTRIES

def get_mode():
    """
    Default: all
    Optional:
      inet  = IPv4 entries only
      inet6 = IPv6 entries only

    Filters by address family only -- direction (src/dst/both) is set per
    entry via the apply-macro, not by a command-line argument.
    """

    args = [a.lower() for a in sys.argv[1:]]

    if "inet" in args:
        return "inet"

    if "inet6" in args:
        return "inet6"

    return "all"

def build_actions(entries, mode):
    """
    Expand each macro entry into one or two concrete clear actions --
    'both' means both a source-prefix and a destination-prefix clear for
    that same prefix.
    """

    actions = []

    for entry in entries:
        if mode != "all" and entry["family"] != mode:
            continue

        direction = entry["direction"]
        prefix = entry["prefix"]

        if direction in ("src", "both"):
            actions.append(("source-prefix", prefix))

        if direction in ("dst", "both"):
            actions.append(("destination-prefix", prefix))

    return actions

def clear_prefix(dev, kind, prefix):
    cmd = f"clear security flow session {kind} {prefix}"

    try:
        rsp = dev.rpc.cli(
            command=cmd,
            format="text"
        )

        text = rsp.text.strip() if rsp.text else "OK"

        return True, text

    except RpcError as err:
        return False, str(err).replace("\n", " ")

    except Exception as err:
        return False, str(err).replace("\n", " ")

def main():
    mode = get_mode()

    try:
        dev = Device()
        dev.open()

    except ConnectError as err:
        print(f"ERROR: Could not connect to local device: {err}")
        return

    entries = get_entries_from_apply_macro(dev)
    actions = build_actions(entries, mode)

    print(f"Mode: {mode}")
    print(f"Clear actions: {len(actions)}")
    print("-" * 80)

    for kind, prefix in actions:
        ok, msg = clear_prefix(dev, kind, prefix)

        if ok:
            print(f"OK   {kind} {prefix}")
        else:
            print(f"FAIL {kind} {prefix} -- {msg}")

    try:
        dev.close()
    except Exception:
        pass

    print("-" * 80)
    print("Done")

if __name__ == "__main__":
    main()
