# dhcp-reservations

On-box Junos Python automation script that reads active DHCP server
lease bindings (`show dhcp server binding`) and writes matching entries
as static reservations under `access address-assignment`, so devices
keep the same IP even after their lease expires.

Originally scoped to only reserve Ruckus APs (matched by MAC OUI). That
matching is currently **disabled** (`ENFORCE_RUCKUS_OUI = False` in
[`dhcp_reservations.py`](dhcp_reservations.py)) while we get the
reservation / commit-check / commit mechanics working end-to-end against
a real box -- right now every DHCP binding is treated as a candidate.
Flip the flag back once that's confirmed.

## Install

Copy the script to the box, then register it as both an op script (for
manual testing) and an event script (for unattended, periodic runs):

```
file copy ftp://... /var/db/scripts/event/dhcp_reservations.py
file copy ftp://... /var/db/scripts/op/dhcp_reservations.py

set system scripts language python
set system scripts op file dhcp_reservations.py
set event-options event-script file dhcp_reservations.py
commit
```

(You can drop the `op file` registration once you no longer need
interactive dry-runs -- see "Known issue" below for why we're keeping it
for now.)

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

## Testing

Manual, interactive, no changes made:

```
run op dhcp_reservations.py dry-run
```

Manual, interactive, loads and commits:

```
run op dhcp_reservations.py
```

Trigger the event-script path without waiting for the timer (verify the
exact syntax with `test event-options ?` on your Junos version -- this
is the command as of recent Junos releases):

```
test event-options policy DHCP_RESERVE_POLICY event DHCP_RESERVE_TIMER
```

Event-script output goes to syslog (tagged `dhcp_reservations`), not to
your terminal -- check with:

```
show log messages | match dhcp_reservations
```

## Known issue (open, pending vsrx test)

An earlier op-script run against a real box got as far as detecting
bindings and building the `set` commands correctly, then failed at
commit-check:

```
[ERROR] Commit check failed, aborting (no changes committed): CommitError(edit_path: None, bad_element: None, message: error: configuration check-out fail
```

The captured output was truncated before the actual reason. Two changes
in this version are meant to get us the full picture on the next test:

1. **Config mode switched from `exclusive` to `private`** (see the
   `CONFIG_MODE` constant). `exclusive` locks the whole box out of
   configuration mode on *every single run* of what's meant to be an
   unattended, periodically-firing script -- a bad property even setting
   the original failure aside. `private` isolates this script's edits
   without blocking other users, at the cost of requiring the shared
   candidate to be clean; the script checks for that up front
   (`candidate_is_clean()`) and logs a specific reason rather than
   surfacing an opaque RPC error.
2. **Full error text and active-session info are now logged** on any
   config-open or commit-check failure, instead of whatever `str(err)`
   happened to fit on one truncated line.

If the `private` mode switch alone doesn't resolve it, the full error
text from the next run should say why.
