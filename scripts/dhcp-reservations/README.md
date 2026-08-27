# dhcp-reservations

On-box Junos Python automation script that reads active DHCP server
lease bindings (`show dhcp server binding`) and writes matching entries
as static reservations under `access address-assignment`, so devices
keep the same IP even after their lease expires.

Verified end-to-end against a real vSRX (22.4R1.10): 100 generic DHCP
bindings in, 100 reservations created; a mixed follow-up batch (10
matching a Ruckus OUI, 20 not) correctly reserved only the 10; reruns
correctly find 0 new (idempotent). Confirmed both as a manual op-script
run and as an unattended event-script firing on a timer.

Only reserves Ruckus APs, matched by MAC OUI against the `RUCKUS_OUIS`
list in [`dhcp_reservations.py`](dhcp_reservations.py)
(`ENFORCE_RUCKUS_OUI = True`). Set that to `False` to reserve every DHCP
binding regardless of vendor.

## Prerequisites (existing box config)

This script only *writes* reservations into an address-assignment pool
that already exists and is actively serving DHCP -- it doesn't create
DHCP service from scratch. Before installing the script, the target
VLAN/interface needs:

```
set access address-assignment pool <POOL> family inet network <subnet>/<mask>
set access address-assignment pool <POOL> family inet range <RANGE-NAME> low <first-ip>
set access address-assignment pool <POOL> family inet range <RANGE-NAME> high <last-ip>
set access address-assignment pool <POOL> family inet dhcp-attributes router <gateway-ip>

set system services dhcp-local-server group <GROUP> interface <iface>.<unit>

set security zones security-zone <ZONE> host-inbound-traffic system-services dhcp
set security zones security-zone <ZONE> interfaces <iface>.<unit>
```

If the `dhcp-local-server group` interface binding is wrong (pointing at
an interface that doesn't exist or isn't the one clients are actually
on) or the zone doesn't permit the `dhcp` system-service inbound, the
server silently hands out zero leases -- `show dhcp server binding`
comes back empty and there's nothing for this script to act on. Check
that first if it looks like nothing is happening.

The script also needs Python enabled for on-box scripting:

```
set system scripts language python3
```

## Install

Copy the script to the box (as both an op script, for manual testing,
and an event script, for unattended periodic runs), then register it:

```
scp dhcp_reservations.py user@device:/var/db/scripts/event/dhcp_reservations.py
scp dhcp_reservations.py user@device:/var/db/scripts/op/dhcp_reservations.py
```

```
set system scripts op file dhcp_reservations.py
set event-options event-script file dhcp_reservations.py python-script-user <a-real-login-user>
commit
```

`python-script-user` is the whole trick, and it's mandatory -- see "Why
python-script-user is required" below. `<a-real-login-user>` needs
enough class permission to enter configuration mode and edit `[edit
access]` -- reusing an existing admin account (as tested) is simplest;
a scoped-down service account works too if you'd rather not grant a
script your admin login's full privilege, it just needs its own
class with at least `access`, `access-control`, and `configure`
permissions.

## Wiring up automatic execution

The script is a reconciliation job, not something tied to a specific
syslog message -- it just needs to run periodically. Use a generated
timer event:

```
set event-options generate-event DHCP_RESERVE_TIMER time-interval 300
set event-options policy DHCP_RESERVE_POLICY events DHCP_RESERVE_TIMER
set event-options policy DHCP_RESERVE_POLICY then event-script dhcp_reservations.py
commit
```

Adjust `time-interval` (seconds) to taste -- 300 = every 5 minutes.

## Why `python-script-user` is required

Verified on Junos 22.4R1.10 (vSRX). `python-script-user` should exist
on other Junos releases too, but the failure mode without it (and the
fix) were only confirmed by testing against a live box, not by reading
documentation -- if you're on a materially different Junos version,
verify `set event-options event-script file <name> python-script-user
?` is accepted before assuming it'll behave identically.

Junos always executes an eventd-triggered script (registered as an
`event-script`, *or* invoked via an event policy's `execute-commands`
action) as the unprivileged OS user `nobody` -- regardless of any
`user-name`/`user-context` attribute on the triggering command, which
only affects CLI-command authorization bookkeeping, not the identity
the Python interpreter actually runs as. `nobody` has no NETCONF login
rights, so this script's local `Device()` connection gets rejected with
`user "nobody" does not have access privileges` on every run.

`python-script-user <user>` (set directly on the `event-script file`
stanza, as shown above) is Junos's real fix: it makes the script's
Python interpreter process itself run as the named user, so the local
NETCONF connection authenticates exactly as it does for a manual
`run op dhcp_reservations.py` from that user's own CLI session -- no
credentials, keys, or extra accounts needed in the script itself. This
is the *only* piece required; nothing else about the script changes
between manual and unattended execution.

(Two more elaborate workarounds were explored and abandoned in favor of
this one-liner: authenticating back to the box's own data-plane address
with an explicit user/password or a dedicated SSH-keyed service account
both work, but both are unnecessary complexity now that
`python-script-user` does the job directly. If you ever see this script
connecting to itself by IP with stored credentials, that's a leftover
from that dead end, not the intended design.)

## Testing

Manual, interactive, no changes made:

```
run op dhcp_reservations.py dry-run
```

Manual, interactive, loads and commits:

```
run op dhcp_reservations.py
```

Event-script output goes to syslog (tagged `dhcp_reservations`), not to
your terminal -- check with:

```
show log messages | match dhcp_reservations
```

## Config mode

The script opens the candidate configuration in `private` mode (see the
`CONFIG_MODE` constant), not `exclusive`. `exclusive` would lock the
whole box out of configuration mode on *every single run* of what's
meant to be an unattended, periodically-firing script. `private`
isolates this script's edits without blocking other users, at the cost
of requiring the shared candidate to be clean; the script checks for
that up front (`candidate_is_clean()`) and logs a specific reason rather
than surfacing an opaque RPC error if it isn't.
