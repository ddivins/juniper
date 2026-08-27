#!/usr/bin/env python
"""
dhcp_reservations.py

On-box Junos Python automation script that converts active DHCP server
lease bindings into static DHCP reservations under
`access address-assignment`.

The same file is registered as BOTH an op script (for manual, interactive
testing) and an event script (for unattended, periodic execution) -- see
README.md in this directory for the exact `set` commands and for how to
trigger a test run without waiting for the real event.

Manual test, no changes made:
    run op dhcp_reservations.py dry-run

Manual test, loads and commits:
    run op dhcp_reservations.py

Automatic (once wired to event-options -- see README):
    fires on its own; nothing to type.

TROUBLESHOOTING: Ruckus-OUI matching is temporarily disabled
(ENFORCE_RUCKUS_OUI = False below), so every DHCP binding is treated as a
reservation candidate regardless of vendor. This is deliberate while we
confirm the reservation / commit-check / commit mechanics work end-to-end
on a real box. Flip it back to True once that's confirmed.
"""

import argparse
import traceback

try:
    import jcs
    ON_BOX = True
except ImportError:
    ON_BOX = False

try:
    from junos import Junos_Context
except ImportError:
    Junos_Context = {}

from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import ConnectError, CommitError, ConfigLoadError, RpcError, LockError

# --- Troubleshooting switches --------------------------------------------

# See module docstring. Set True once reservation creation is confirmed
# working and you want to go back to only matching Ruckus APs.
ENFORCE_RUCKUS_OUI = False

# 'private' gives this script its own isolated candidate instead of
# locking every user out of configuration mode on every single run,
# which is what 'exclusive' does -- a bad property for a script that
# fires unattended and repeatedly (event/timer triggered). Private mode
# does require the shared candidate to be clean (no other outstanding
# uncommitted edits); we check for that up front and log a clear reason
# instead of failing with an opaque RPC error.
CONFIG_MODE = "private"

SCRIPT_TAG = "dhcp_reservations"

# All known Ruckus OUIs. Unused while ENFORCE_RUCKUS_OUI is False, kept
# for when we re-enable vendor matching.
RUCKUS_OUIS = {
    "00:13:92", "00:1D:2E", "00:1F:41", "00:22:7F", "00:24:82", "00:25:C4", "00:33:58", "00:E6:3A", "04:4F:AA", "0C:F4:D5",
    "10:F0:68", "18:4B:0D", "18:7C:0B", "1C:3A:60", "1C:B9:C4",
    "20:58:69", "24:79:2A", "24:C9:A1", "28:B3:71", "2C:5D:93", "2C:AB:46", "2C:C5:D3", "2C:E6:CC",
    "30:87:D9", "34:15:93", "34:20:E3", "34:8F:27", "34:FA:9F", "38:45:3B", "38:FF:36", "3C:46:A1",
    "40:B8:2D", "44:1E:98", "4C:B1:CD",
    "50:A7:33", "54:3D:37", "54:EC:2F", "58:93:96", "58:B6:33", "58:FB:96", "5C:83:6C", "5C:DF:89",
    "60:D0:2C", "68:92:34", "68:FD:E8", "6C:AA:B3",
    "70:32:0C", "70:47:77", "70:B2:58", "70:CA:97", "74:31:7E", "74:3E:2B", "74:91:1A", "78:9F:6A",
    "80:03:84", "80:BC:37", "80:F0:CF", "84:18:3A", "84:23:88", "8C:0C:90", "8C:7A:15", "8C:FE:74",
    "90:3A:72", "94:B3:4F", "94:BF:C4", "94:F6:65",
    "A8:0B:FB", "AC:67:06", "AC:DE:01",
    "B0:7C:51", "B4:79:C8", "B4:E5:3E", "BC:9C:8D",
    "C0:8A:DE", "C0:C5:20", "C0:C7:0A", "C4:01:7C", "C4:10:8A", "C8:03:F5", "C8:08:73", "C8:84:8C", "C8:A6:08", "CC:1B:5A", "CC:2D:D2",
    "D0:4F:58", "D4:68:4D", "D4:BD:4F", "D4:C1:9E", "D8:38:FC", "DC:AE:EB",
    "E0:10:7F", "E8:1D:A8", "E8:FC:5F", "EC:58:EA", "EC:8C:A2",
    "F0:3E:90", "F0:6F:CE", "F0:B0:52", "F8:E7:1E", "FC:5C:45", "00:E0:4C", "54:4B:8C", "5C:5B:35", "AC:F4:73"
}


def log(severity, message):
    """
    Log a message. On-box this writes to syslog via jcs so it's visible
    when the script is running unattended as an event script (no
    interactive terminal to print to). Off-box, or if jcs is unavailable
    for any reason, falls back to print().
    """
    line = f"{SCRIPT_TAG}: {message}"
    if ON_BOX:
        try:
            jcs.syslog(f"external.{severity}", line)
            return
        except Exception:
            pass
    print(f"[{severity.upper()}] {line}")


def get_existing_reservations(dev):
    """
    Return a set of upper-case, colon-delimited MAC addresses that
    already have a static DHCP reservation configured under
    access address-assignment, so we don't reload duplicates.
    """
    existing = set()
    try:
        cfg = dev.rpc.get_config(
            filter_xml='<configuration><access><address-assignment/></access></configuration>'
        )
        for hwaddr in cfg.xpath('.//hardware-address'):
            if hwaddr.text:
                existing.add(hwaddr.text.strip().upper())
    except Exception as err:
        log("warning", f"Could not retrieve existing reservations: {err}")
        log("warning", "Proceeding without duplicate-check (may reload existing entries).")
    return existing


def candidate_is_clean(dev):
    """
    True if the shared/default candidate configuration has no
    outstanding uncommitted changes. 'private' mode refuses to open
    otherwise, with an error that doesn't say why -- so we check first
    and log a clear reason instead.
    """
    try:
        diff = dev.rpc.get_config(options={'compare': 'rollback', 'rollback': '0'})
        # PyEZ returns True (not an XML element) when there's no diff at all.
        if isinstance(diff, bool):
            return diff
        text = diff.text if diff is not None else None
        return not (text and text.strip())
    except Exception as err:
        log("warning", f"Could not verify shared candidate is clean: {err}")
        return True  # best-effort; let Config() surface the real error if this guess is wrong


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert DHCP server bindings into static reservations."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and log set commands without loading or committing any configuration."
    )
    # Junos passes both op-script and event-script arguments as key=value
    # strings (e.g. 'dry-run' from `run op dhcp_reservations.py dry-run`,
    # or from a configured `argument dry-run value true` stanza).
    # parse_known_args tolerates that form without erroring on tokens
    # argparse doesn't recognize.
    args, _ = parser.parse_known_args()
    return args


def main():
    args = parse_args()

    trigger = "manual"
    if isinstance(Junos_Context, dict):
        event_context = Junos_Context.get('event-context')
        if event_context:
            trigger = event_context.get('event-name', 'event')

    log("info", f"Starting (trigger={trigger}, dry_run={args.dry_run}, enforce_ruckus_oui={ENFORCE_RUCKUS_OUI})")

    # gather_facts=False speeds up on-box connection since the
    # platform/version is already known locally.
    dev = Device(gather_facts=False, timeout=300)

    try:
        dev.open()
    except ConnectError as err:
        log("error", f"Could not open local NETCONF session: {err}")
        return

    try:
        try:
            dhcp_info = dev.rpc.get_dhcp_server_binding_information(detail=True)
        except Exception as err:
            log("error", f"DHCP binding RPC failed: {err}")
            return

        bindings = dhcp_info.xpath('.//dhcp-binding')
        log("info", f"Bindings found: {len(bindings)}")

        existing_macs = get_existing_reservations(dev)
        log("info", f"Existing reservations found: {len(existing_macs)}")

        set_commands = []
        matched_count = 0

        for binding in bindings:
            mac = binding.findtext('mac-address')
            ip = binding.findtext('allocated-address')
            pool = binding.findtext('pool-name')

            if not (mac and ip and pool):
                continue

            mac_upper = mac.upper()
            oui = mac_upper[:8]

            log("info", f"IP={ip}  MAC={mac_upper}  POOL={pool}  OUI={oui}")

            if ENFORCE_RUCKUS_OUI and oui not in RUCKUS_OUIS:
                continue

            matched_count += 1

            if mac_upper in existing_macs:
                log("info", f"Reservation already exists for {mac_upper}, skipping.")
                continue

            hostname = f"ruckus-{mac_upper.replace(':', '')}"
            cmd = (
                f"set access address-assignment pool {pool} family inet "
                f"host {hostname} hardware-address {mac} ip-address {ip}"
            )
            set_commands.append(cmd)
            log("info", f"[NEW] {cmd}")

        log("info", f"Devices matched: {matched_count}")
        log("info", f"New reservations to create: {len(set_commands)}")

        if not set_commands:
            log("info", "No new reservations needed.")
            return

        if args.dry_run:
            log("info", "[DRY-RUN] The following commands would be applied:")
            for cmd in set_commands:
                log("info", f"  {cmd}")
            log("info", "[DRY-RUN] No configuration was loaded or committed.")
            return

        if CONFIG_MODE == "private" and not candidate_is_clean(dev):
            log("error",
                "Shared candidate configuration has uncommitted changes; "
                "refusing to open a private session rather than risk "
                "stomping on someone else's in-progress edit. Have "
                "someone commit or rollback the pending change; this "
                "script will pick the work back up on its next trigger.")
            return

        try:
            cu = Config(dev, mode=CONFIG_MODE)
            cu.__enter__()
        except (RpcError, LockError) as err:
            log("error", f"Could not open {CONFIG_MODE} candidate configuration: {err}")
            log("error", f"Full error detail: {err!r}")
            try:
                users = dev.rpc.get_system_users_information()
                log("error", f"Active sessions: {users.text.strip()}")
            except Exception:
                pass
            return

        try:
            try:
                for cmd in set_commands:
                    cu.load(cmd, format='set')
            except ConfigLoadError as err:
                log("error", f"Failed to load configuration: {err}")
                return

            try:
                log("info", "Running commit check...")
                # The on-box PyEZ build doesn't accept timeout= here (older
                # signature than commit()'s); dev.timeout still bounds the
                # underlying RPC.
                cu.commit_check()
                log("info", "Commit check passed.")
            except CommitError as err:
                log("error", f"Commit check failed, aborting (no changes committed): {err}")
                log("error", f"Full error detail: {err!r}")
                return
            except Exception as err:
                log("error", f"Unexpected error during commit check: {err}")
                log("error", traceback.format_exc())
                return

            try:
                cu.commit(
                    ignore_warning=True,
                    comment=f"Automated DHCP reservations (trigger={trigger})",
                    timeout=360
                )
                log("info", "Configuration committed successfully.")
            except CommitError as err:
                log("error", f"Commit failed: {err}")
                log("error", f"Full error detail: {err!r}")
                return
        finally:
            cu.__exit__(None, None, None)

    finally:
        dev.close()


if __name__ == '__main__':
    main()
