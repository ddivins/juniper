#!/usr/bin/env python3

from jnpr.junos import Device
from jnpr.junos.exception import RpcError, ConnectError
from lxml import etree
import re

MACRO_NAME = "SRX-IF-STATS"
DEBUG = False

DEFAULT_INTERFACES = [
    "ae0",
]

def fmt_bps(value):
    try:
        bps = int(value)
    except Exception:
        return "0 bps"

    if bps >= 1_000_000_000:
        return f"{bps / 1_000_000_000:.2f} Gbps"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    if bps >= 1_000:
        return f"{bps / 1_000:.2f} Kbps"

    return f"{bps:,} bps"

def fmt_num(value):
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"

def get_text(elem, path, default="0"):
    found = elem.find(path)

    if found is not None and found.text:
        return found.text.strip()

    return default

def get_desc(elem):
    desc = elem.find("description")
    return desc.text.strip() if desc is not None and desc.text else ""

def debug_print(msg):
    if DEBUG:
        print(f"DEBUG: {msg}")

def interface_sort_key(item):
    name, value = item

    match = re.search(r"interface-(\d+)", name)
    if match:
        return int(match.group(1))

    return 9999

def parse_apply_macro_interfaces(xml_root, source_name):
    found = []

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

            if name.startswith("interface-") and value:
                found.append((name, value))

    found.sort(key=interface_sort_key)

    return [value for name, value in found]

def get_interfaces_from_apply_macro(dev):
    interfaces = []

    try:
        rsp = dev.rpc.cli(
            command=f"show configuration apply-macro {MACRO_NAME}",
            format="xml"
        )

        interfaces = parse_apply_macro_interfaces(
            rsp,
            "cli show configuration apply-macro"
        )

    except Exception as err:
        debug_print(f"cli show configuration apply-macro failed: {err}")

    if interfaces:
        debug_print(f"using interfaces from apply-macro: {interfaces}")
        return interfaces

    try:
        cfg = dev.rpc.get_config(
            options={"database": "committed"}
        )

        interfaces = parse_apply_macro_interfaces(
            cfg,
            "get_config committed"
        )

    except Exception as err:
        debug_print(f"get_config committed failed: {err}")

    if interfaces:
        debug_print(f"using interfaces from committed config: {interfaces}")
        return interfaces

    debug_print(f"no apply-macro interfaces found; falling back to {DEFAULT_INTERFACES}")

    return DEFAULT_INTERFACES

def get_drop_total(elem, direction):
    if direction == "in":
        paths = [
            "input-error-list/input-drops",
            "input-error-list/input-discards",
            "input-error-list/input-errors",
        ]
    else:
        paths = [
            "output-error-list/output-drops",
            "output-error-list/output-discards",
            "output-error-list/output-errors",
        ]

    total = 0

    for path in paths:
        try:
            total += int(get_text(elem, path, "0"))
        except Exception:
            pass

    return total

def add_error_row(rows, iface, msg):
    rows.append([
        iface,
        "ERROR",
        "-",
        "-",
        "-",
        msg,
    ])

def get_flow_session_summary(dev):
    data = {
        "total_sessions": "N/A",
        "offload_sessions": "N/A",
    }

    try:
        rsp = dev.rpc.cli(
            command="show security flow session summary",
            format="text"
        )

        text = rsp.text or ""

        for line in text.splitlines():
            line = line.strip()

            if line.startswith("Sessions-in-use:"):
                data["total_sessions"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

            elif line.startswith("Services-offload-sessions:"):
                data["offload_sessions"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

    except Exception:
        pass

    return data

def get_security_monitoring(dev):
    data = {
        "spu_cpu": "N/A",
        "spu_mem": "N/A",
        "ipv4_sessions": "N/A",
        "ipv6_sessions": "N/A",
        "total_cps": "N/A",
        "ipv4_cps": "N/A",
        "ipv6_cps": "N/A",
    }

    try:
        rsp = dev.rpc.cli(
            command="show security monitoring fpc 0",
            format="text"
        )

        text = rsp.text or ""

        for line in text.splitlines():
            line = line.strip()

            if line.startswith("CPU utilization"):
                data["spu_cpu"] = line.split(":", 1)[1].strip()

            elif line.startswith("Memory utilization"):
                data["spu_mem"] = line.split(":", 1)[1].strip()

            elif line.startswith("Current flow session IPv4"):
                data["ipv4_sessions"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

            elif line.startswith("Current flow session IPv6"):
                data["ipv6_sessions"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

            elif line.startswith("Total Session Creation Per Second"):
                data["total_cps"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

            elif line.startswith("IPv4  Session Creation Per Second"):
                data["ipv4_cps"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

            elif line.startswith("IPv6  Session Creation Per Second"):
                data["ipv6_cps"] = fmt_num(
                    line.split(":", 1)[1].strip()
                )

    except Exception:
        pass

    return data

def main():
    rows = []
    total_bps_in = 0
    total_bps_out = 0

    try:
        dev = Device()
        dev.open()

    except ConnectError as err:
        print(f"ERROR: Could not connect to local device: {err}")
        return

    interfaces = get_interfaces_from_apply_macro(dev)

    for iface in interfaces:
        try:
            rsp = dev.rpc.get_interface_information(
                interface_name=iface,
                extensive=True
            )

            phy = rsp.find(".//physical-interface")

            if phy is None:
                add_error_row(rows, iface, "not found")
                continue

            name = get_text(phy, "name", iface)
            desc = get_desc(phy)

            bps_in = get_text(phy, "traffic-statistics/input-bps", "0")
            bps_out = get_text(phy, "traffic-statistics/output-bps", "0")

            try:
                total_bps_in += int(bps_in)
            except Exception:
                pass

            try:
                total_bps_out += int(bps_out)
            except Exception:
                pass

            drops_in = get_drop_total(phy, "in")
            drops_out = get_drop_total(phy, "out")

            rows.append([
                name,
                desc,
                fmt_bps(bps_in),
                fmt_bps(bps_out),
                f"{drops_in:,}",
                f"{drops_out:,}",
            ])

        except RpcError as err:
            err_msg = str(err).replace("\n", " ")

            if "not found" in err_msg.lower():
                add_error_row(rows, iface, "not found")
            else:
                add_error_row(rows, iface, err_msg[:40])

            continue

        except Exception as err:
            add_error_row(
                rows,
                iface,
                f"script error: {str(err)[:40]}"
            )
            continue

    flow_data = get_flow_session_summary(dev)
    monitoring_data = get_security_monitoring(dev)

    try:
        dev.close()
    except Exception:
        pass

    headers = [
        "Interface",
        "Description",
        "bps in",
        "bps out",
        "drops in",
        "drops out / status",
    ]

    widths = [14, 35, 16, 16, 12, 24]

    print(" ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("-" * sum(widths))

    for row in rows:
        print(" ".join(str(v).ljust(w)[:w] for v, w in zip(row, widths)))

    print("-" * sum(widths))

    print(
        " ".join([
            "TOTAL".ljust(widths[0]),
            "".ljust(widths[1]),
            fmt_bps(total_bps_in).ljust(widths[2]),
            fmt_bps(total_bps_out).ljust(widths[3]),
            "".ljust(widths[4]),
            "".ljust(widths[5]),
        ])
    )

    print(
        " ".join([
            "COMBINED".ljust(widths[0]),
            "".ljust(widths[1]),
            fmt_bps(total_bps_in + total_bps_out).ljust(widths[2]),
            "".ljust(widths[3]),
            "".ljust(widths[4]),
            "".ljust(widths[5]),
        ])
    )

    print("-" * sum(widths))
    print("SRX SUMMARY")
    print("-" * 60)

    print(f"SPU CPU Utilization : {monitoring_data['spu_cpu']}")
    print(f"SPU Memory Usage    : {monitoring_data['spu_mem']}")
    print(f"Total Sessions      : {flow_data['total_sessions']}")
    print(f"Offload Sessions    : {flow_data['offload_sessions']}")
    print(f"IPv4 Sessions       : {monitoring_data['ipv4_sessions']}")
    print(f"IPv6 Sessions       : {monitoring_data['ipv6_sessions']}")
    print(f"Total Session CPS   : {monitoring_data['total_cps']}")
    print(f"IPv4 Session CPS    : {monitoring_data['ipv4_cps']}")
    print(f"IPv6 Session CPS    : {monitoring_data['ipv6_cps']}")

if __name__ == "__main__":
    main()
