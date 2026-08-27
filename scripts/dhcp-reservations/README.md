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

## Copying the file

The script is registered as both an op script (manual testing) and an
event script (unattended runs) -- copy the same file to both
locations:

```
scp dhcp_reservations.py user@device:/var/db/scripts/event/dhcp_reservations.py
scp dhcp_reservations.py user@device:/var/db/scripts/op/dhcp_reservations.py
```

No `chmod` needed. Junos invokes op/event scripts through its own
script engine (keyed off `system scripts language python3` and the
`file` registration in config), not via a direct OS `execve()` that
would care about the executable bit -- the default permissions `scp`
leaves the file with (`-rw-r--r--`) are enough, confirmed by every run
in testing.

## Required configuration (one block)

Everything below needs to be in place for the script to do anything
useful. Load all of this in one pass:

```
# 1. Enable Python for on-box scripts.
set system scripts language python3

# 2. The DHCP service this script writes reservations into. Must
#    already exist and actually be handing out leases -- this script
#    only adds static hosts to a pool, it doesn't create DHCP service.
#    Substitute your own pool/range/subnet/interface/zone names.
set access address-assignment pool <POOL> family inet network <subnet>/<mask>
set access address-assignment pool <POOL> family inet range <RANGE-NAME> low <first-ip>
set access address-assignment pool <POOL> family inet range <RANGE-NAME> high <last-ip>
set access address-assignment pool <POOL> family inet dhcp-attributes router <gateway-ip>
set system services dhcp-local-server group <GROUP> interface <iface>.<unit>
set security zones security-zone <ZONE> host-inbound-traffic system-services dhcp
set security zones security-zone <ZONE> interfaces <iface>.<unit>

# 3. Register the script as both an op script (manual testing) and an
#    event script (unattended runs). <login-user> is who the script
#    actually runs as -- see "Why python-script-user is required".
set system scripts op file dhcp_reservations.py
set event-options event-script file dhcp_reservations.py python-script-user <login-user>

# 4. Trigger it on a timer -- this is a reconciliation job, not tied
#    to a specific syslog message. Adjust time-interval (seconds) to
#    taste; 300 = every 5 minutes.
set event-options generate-event DHCP_RESERVE_TIMER time-interval 300
set event-options policy DHCP_RESERVE_POLICY events DHCP_RESERVE_TIMER
set event-options policy DHCP_RESERVE_POLICY then event-script dhcp_reservations.py

commit
```

Verified working example, straight from a tested box (pool/interface
names are this lab's, `python-script-user jcluser` reuses the existing
admin login -- see the permission-scoping note below if you'd rather
not do that):

```
set system scripts language python3
set access address-assignment pool DHCP-POOL-01 family inet network 10.10.1.0/24
set access address-assignment pool DHCP-POOL-01 family inet range r1 low 10.10.1.100
set access address-assignment pool DHCP-POOL-01 family inet range r1 high 10.10.1.254
set access address-assignment pool DHCP-POOL-01 family inet dhcp-attributes router 10.10.1.1
set system services dhcp-local-server group DHCP-POOL-01 interface ge-0/0/1.0
set security zones security-zone TRUST host-inbound-traffic system-services dhcp
set security zones security-zone TRUST interfaces ge-0/0/1.0
set system scripts op file dhcp_reservations.py
set event-options event-script file dhcp_reservations.py python-script-user jcluser
set event-options generate-event DHCP_RESERVE_TIMER time-interval 300
set event-options policy DHCP_RESERVE_POLICY events DHCP_RESERVE_TIMER
set event-options policy DHCP_RESERVE_POLICY then event-script dhcp_reservations.py
commit
```

If the `dhcp-local-server group` interface binding is wrong (pointing
at an interface that doesn't exist, or isn't the one clients are
actually on) or the zone doesn't permit the `dhcp` system-service
inbound, the server silently hands out zero leases -- `show dhcp
server binding` comes back empty and there's nothing for this script
to act on. Check that first if it looks like nothing is happening.

`<login-user>` needs enough class permission to enter configuration
mode and edit `[edit access]`. Reusing an existing admin account (as
tested, `jcluser` above) is simplest. A scoped-down service account
works too, if you'd rather not grant a script your admin login's full
privilege -- give it its own login class with at least `access`,
`access-control`, and `configure` permissions:

```
set system login class dhcp-reservations permissions access
set system login class dhcp-reservations permissions access-control
set system login class dhcp-reservations permissions configure
set system login user <login-user> class dhcp-reservations
```

That last piece (creating the account itself, with a password or SSH
key) isn't shown here on purpose -- do that step by hand on the box
rather than scripting/committing credentials.

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

## Troubleshooting

Start with syslog -- almost everything the script does is logged there,
tagged `dhcp_reservations`:

```
show log messages | match dhcp_reservations
```

**`Bindings found: 0`, or the script never seems to run at all.**
DHCP isn't actually handing out leases, or nothing's reaching the
script. Check `show dhcp server binding` directly -- if that's empty
too, this isn't a script problem, it's the `dhcp-local-server group`
interface binding or the zone's `dhcp` system-service (see "Required
configuration" above). If bindings exist but the script never logs
anything, confirm the event policy actually fired: `show log messages
| match EVENTD_ESCRIPT_EXECUTION`.

**`Could not open local NETCONF session: ... user "nobody" does not
have access privileges`.** Missing `python-script-user` on the
`event-script file` stanza -- see "Why python-script-user is required"
above. This is the single most common failure mode; check it first.

**Check `<login-user>`'s permissions.** If the script gets past opening
a connection but fails loading or committing the config, the identity
it's running as (whatever `python-script-user` points at) likely
doesn't have enough class permission. Check what it's actually
configured with:

```
show configuration system login user <login-user> | display set
show configuration system login class <class-name> | display set
```

It needs `configure` (to enter configuration mode at all) plus enough
scope over `[edit access]` to create hosts under
`address-assignment` -- `access` and `access-control` cover that (see
the scoped-account example above), or a broader class like
`super-user` obviously already includes it. The quickest direct test
is to log in as that user yourself and try the same thing by hand:

```
ssh <login-user>@device
run op dhcp_reservations.py dry-run
configure
set access address-assignment pool <POOL> family inet host test-perm hardware-address 00:00:00:00:00:01 ip-address <unused-ip-in-pool>
commit check
rollback 0
exit
```

If `commit check` fails there with a permission error, that's the
class, not the script.

**Commit fails with something like `configuration check-out fail`, or
`private` mode refuses to open.** Usually means the shared candidate
configuration already has uncommitted changes sitting in it from
someone else's session -- `private` mode won't open on top of a dirty
shared candidate (this is exactly what `candidate_is_clean()` checks
for and logs a clear reason for; if you're seeing the raw RPC error
instead, something changed the config between that check and the
`Config()` open). Look for a stale session:

```
show system users
```

If there's an idle session that's been sitting in `configure` mode,
either have that user finish up (`commit` or `rollback 0; exit`), or
clear it yourself: `request system logout terminal <tty>` (the `TTY`
column from `show system users`, e.g. `pts/0`).

**`CSCRIPT_SECURITY_WARNING: unsigned python script ... without
checksum is executed`.** Expected, shows up on every single run in
syslog, not an error -- Junos supports signed/checksummed scripts for
stricter environments, but nothing here requires it.

**Ruckus devices aren't getting reservations even though they're
bound.** Check the binding's actual OUI against `RUCKUS_OUIS` in
[`dhcp_reservations.py`](dhcp_reservations.py) -- the syslog line
`IP=... MAC=... POOL=... OUI=...` is logged for *every* binding
regardless of match, so you can see exactly what OUI the script saw
and compare it to the list. A device whose vendor changed MACs or
whose OUI just isn't in the (necessarily incomplete) list will be
skipped silently -- that's `ENFORCE_RUCKUS_OUI` working as intended,
not a bug, but worth confirming that's actually what's happening.
