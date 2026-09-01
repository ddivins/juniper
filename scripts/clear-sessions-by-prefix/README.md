# clear-sessions-by-prefix

On-box Junos Python **op script** that clears active flow sessions for a
configurable list of IPv4/IPv6 prefixes -- e.g. after a policy or NAT
change, to force affected traffic to re-establish sessions under the new
rules instead of waiting for the old ones to time out. Each configured
prefix can be cleared by source, by destination, or both.

Depending on how each prefix is configured (see below), it runs one or
both of:

```
clear security flow session source-prefix <prefix>
clear security flow session destination-prefix <prefix>
```

and reports success/failure per command run.

## Configuring the prefixes

Prefixes come from a top-level `apply-macro` named `CLEAR-SESSIONS-PREFIXES`,
not from anything hardcoded in the script. Each data entry's *name* encodes
both which side to clear and the address family; its *value* is the
prefix:

```
<direction>-<family>-<n>
```

- `direction` -- `src`, `dst`, or `both`
- `family` -- `inet` (IPv4) or `inet6` (IPv6)
- `n` -- controls clear order only, doesn't need to be contiguous

```
set apply-macro CLEAR-SESSIONS-PREFIXES dst-inet-1 10.96.0.0/11
set apply-macro CLEAR-SESSIONS-PREFIXES dst-inet-2 10.128.0.0/9
set apply-macro CLEAR-SESSIONS-PREFIXES src-inet6-1 2000::/16
set apply-macro CLEAR-SESSIONS-PREFIXES both-inet-1 10.50.0.0/16
commit
```

The example above clears: `10.96.0.0/11` and `10.128.0.0/9` by
destination, `2000::/16` by source, and `10.50.0.0/16` by **both**
source and destination (two separate clear commands for that one entry).

Lookup order, first hit wins (same pattern as
[`srx-if-stats`](../srx-if-stats/)):

1. `show configuration apply-macro CLEAR-SESSIONS-PREFIXES` (op-mode CLI)
2. the committed configuration directly, via `get_config`
   (`options={'database': 'committed'}`), if (1) comes back empty
3. `DEFAULT_ENTRIES` in
   [`clear-sessions-by-prefix.py`](clear-sessions-by-prefix.py) if the
   macro isn't found at all -- deliberately empty, so with no macro
   configured the script clears nothing rather than guessing.

A data entry whose name doesn't match `<src|dst|both>-<inet|inet6>-<n>`
is skipped (logged when `DEBUG = True`, at the top of the script) rather
than erroring out the whole run.

## Setup

```
set system scripts language python3
set apply-macro CLEAR-SESSIONS-PREFIXES dst-inet-1 <prefix>
# repeat with src-/dst-/both- and inet/inet6 for every prefix to clear
set system scripts op file clear-sessions-by-prefix.py
commit
```

Copy the script into place (no `chmod` needed -- see the
`dhcp-reservations` README's "Copying the file" note for why):

```
scp clear-sessions-by-prefix.py user@device:/var/db/scripts/op/clear-sessions-by-prefix.py
```

## Running it

```
run op clear-sessions-by-prefix.py          # all configured entries
run op clear-sessions-by-prefix.py inet      # inet (IPv4) entries only
run op clear-sessions-by-prefix.py inet6     # inet6 (IPv6) entries only
```

The `inet`/`inet6` argument filters by address family only. Direction
(src/dst/both) is fixed per entry in the apply-macro, not selectable at
run time.

## Notes

- Only issues `clear security flow session source-prefix|destination-prefix
  <prefix>` -- it never touches the candidate configuration.
- Each clear command runs independently; a failure on one is reported and
  the script continues on to the rest. A `both` entry that fails on one
  side still attempts the other.
