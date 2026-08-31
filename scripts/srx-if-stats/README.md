# srx-if-stats

On-box Junos Python **op script** (read-only, no configuration changes) that
prints a single dashboard-style report combining:

- per-interface bandwidth (bps in/out) and error/discard/drop counts, for a
  configurable list of interfaces
- totals and a combined in+out bandwidth figure across those interfaces
- an SRX summary: SPU CPU/memory utilization, flow session counts (total and
  offloaded), and session-creation-per-second, from `show security
  monitoring fpc 0` and `show security flow session summary`

## Which interfaces get polled

The script looks for a top-level `apply-macro` named `SRX-IF-STATS` holding
one `interface-N` data entry per interface to poll, in order:

```
set apply-macro SRX-IF-STATS interface-1 ae0
set apply-macro SRX-IF-STATS interface-2 ge-0/0/1
commit
```

Lookup order, first hit wins:

1. `show configuration apply-macro SRX-IF-STATS` (op-mode CLI, works from an
   unprivileged run)
2. the committed configuration directly, via `get_config`
   (`options={'database': 'committed'}`), as a fallback if (1) comes back
   empty
3. `DEFAULT_INTERFACES` in [`srx-if-stats.py`](srx-if-stats.py) (currently
   `["ae0"]`) if neither of the above finds the macro

Set `DEBUG = True` at the top of the script to log each step of that lookup
(and each per-macro data entry found) to stdout.

## Setup

```
set system scripts language python3
set apply-macro SRX-IF-STATS interface-1 <iface>
# repeat interface-2, interface-3, ... for every interface to report on
set system scripts op file srx-if-stats.py
commit
```

Copy the script itself into place (no `chmod` needed -- see the
`dhcp-reservations` README's "Copying the file" note for why):

```
scp srx-if-stats.py user@device:/var/db/scripts/op/srx-if-stats.py
```

## Running it

```
run op srx-if-stats.py
```

Output is a plain-text table to the terminal -- this is an interactive
report, not something registered as an event script or intended to run
unattended.

## Notes

- Purely read-only: it only issues `get_interface_information`,
  `show security flow session summary`, and `show security monitoring fpc
  0` RPCs/CLI calls. It never opens or touches the candidate configuration.
- Each interface is handled independently -- an interface that doesn't
  exist, or an RPC error for one interface, shows up as an `ERROR` row for
  that interface only and doesn't abort the rest of the report.
- Uses the default on-box `Device()` connection (local NETCONF), so it runs
  as whatever user invokes `run op srx-if-stats.py`.
