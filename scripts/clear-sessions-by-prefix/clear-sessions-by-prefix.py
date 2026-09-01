#!/usr/bin/env python3

from jnpr.junos import Device
from jnpr.junos.exception import RpcError, ConnectError
import re
import sys

MACRO_NAME = "CLEAR-SESSIONS-PREFIXES"
DEBUG = False

# Used only if the apply-macro isn't configured at all (see README).
# Deliberately empty: with no macro configured, the script should clear
# nothing rather than silently fall back to some previously hardcoded set
# of prefixes.
DEFAULT_IPV4_PREFIXES = []

DEFAULT_IPV6_PREFIXES = []

def debug_print(msg):
    if DEBUG:
        print(f"DEBUG: {msg}")

def prefix_sort_key(item):
    name, value = item

    match = re.search(r"-(\d+)$", name)
    if match:
        return int(match.group(1))

    return 9999

def parse_apply_macro_prefixes(xml_root, source_name):
    ipv4 = []
    ipv6 = []

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

            if name.startswith("ipv4-"):
                ipv4.append((name, value))
            elif name.startswith("ipv6-"):
                ipv6.append((name, value))

    ipv4.sort(key=prefix_sort_key)
    ipv6.sort(key=prefix_sort_key)

    return [v for _, v in ipv4], [v for _, v in ipv6]

def get_prefixes_from_apply_macro(dev):
    try:
        rsp = dev.rpc.cli(
            command=f"show configuration apply-macro {MACRO_NAME}",
            format="xml"
        )

        ipv4, ipv6 = parse_apply_macro_prefixes(
            rsp,
            "cli show configuration apply-macro"
        )

        if ipv4 or ipv6:
            debug_print(f"using prefixes from apply-macro: ipv4={ipv4} ipv6={ipv6}")
            return ipv4, ipv6

    except Exception as err:
        debug_print(f"cli show configuration apply-macro failed: {err}")

    try:
        cfg = dev.rpc.get_config(
            options={"database": "committed"}
        )

        ipv4, ipv6 = parse_apply_macro_prefixes(
            cfg,
            "get_config committed"
        )

        if ipv4 or ipv6:
            debug_print(f"using prefixes from committed config: ipv4={ipv4} ipv6={ipv6}")
            return ipv4, ipv6

    except Exception as err:
        debug_print(f"get_config committed failed: {err}")

    debug_print(
        f"no apply-macro prefixes found; falling back to defaults "
        f"ipv4={DEFAULT_IPV4_PREFIXES} ipv6={DEFAULT_IPV6_PREFIXES}"
    )

    return DEFAULT_IPV4_PREFIXES, DEFAULT_IPV6_PREFIXES

def get_mode():
    """
    Default: all
    Optional:
      inet  = IPv4 only
      inet6 = IPv6 only
    """

    args = [a.lower() for a in sys.argv[1:]]

    if "inet" in args:
        return "inet"

    if "inet6" in args:
        return "inet6"

    return "all"

def clear_prefix(dev, prefix):
    cmd = f"clear security flow session destination-prefix {prefix}"

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

    ipv4_prefixes, ipv6_prefixes = get_prefixes_from_apply_macro(dev)

    if mode == "inet":
        prefixes = ipv4_prefixes
    elif mode == "inet6":
        prefixes = ipv6_prefixes
    else:
        prefixes = ipv4_prefixes + ipv6_prefixes

    print(f"Mode: {mode}")
    print(f"Prefixes to clear: {len(prefixes)}")
    print("-" * 80)

    for prefix in prefixes:
        ok, msg = clear_prefix(dev, prefix)

        if ok:
            print(f"OK   destination-prefix {prefix}")
        else:
            print(f"FAIL destination-prefix {prefix} -- {msg}")

    try:
        dev.close()
    except Exception:
        pass

    print("-" * 80)
    print("Done")

if __name__ == "__main__":
    main()
