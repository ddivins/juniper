# clear-sessions-by-prefix

On-box Junos Python **op script** that clears active flow sessions for a
configurable list of IPv4/IPv6 destination prefixes -- e.g. after a policy
or NAT change, to force affected traffic to re-establish sessions under
the new rules instead of waiting for the old ones to time out.

For each configured prefix it runs:

```
clear security flow session destination-prefix <prefix>
```

and reports success/failure per prefix.

## Configuring the prefixes

Prefixes come from a top-level `apply-macro` named `CLEAR-SESSIONS-PREFIXES`,
not from anything hardcoded in the script. IPv4 entries are named `ipv4-N`,
IPv6 entries `ipv6-N` (the number only controls display/clear order):

```
set apply-macro CLEAR-SESSIONS-PREFIXES ipv4-1 10.96.0.0/11
set apply-macro CLEAR-SESSIONS-PREFIXES ipv4-2 10.128.0.0/9
set apply-macro CLEAR-SESSIONS-PREFIXES ipv6-1 2000::/16
commit
```

Lookup order, first hit wins (same pattern as
[`srx-if-stats`](../srx-if-stats/)):

1. `show configuration apply-macro CLEAR-SESSIONS-PREFIXES` (op-mode CLI)
2. the committed configuration directly, via `get_config`
   (`options={'database': 'committed'}`), if (1) comes back empty
3. `DEFAULT_IPV4_PREFIXES` / `DEFAULT_IPV6_PREFIXES` in
   [`clear-sessions-by-prefix.py`](clear-sessions-by-prefix.py) if the
   macro isn't found at all -- both are deliberately empty, so with no
   macro configured the script clears nothing rather than guessing.

The macro is matched and used as a whole per family: if you set any
`ipv4-N` entries, those entries -- not the built-in defaults -- become the
full IPv4 list (same for `ipv6-N`/IPv6). Set `DEBUG = True` at the top of
the script to log each step of the lookup and every macro entry found.

## Setup

```
set system scripts language python3
set apply-macro CLEAR-SESSIONS-PREFIXES ipv4-1 <prefix>
# repeat ipv4-2, ipv6-1, ... for every prefix to clear
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
run op clear-sessions-by-prefix.py          # clears both IPv4 and IPv6 prefixes
run op clear-sessions-by-prefix.py inet      # IPv4 prefixes only
run op clear-sessions-by-prefix.py inet6     # IPv6 prefixes only
```

## Notes

- Only issues `clear security flow session destination-prefix <prefix>` --
  it never touches the candidate configuration.
- Each prefix is cleared independently; a failure on one prefix is reported
  and the script continues on to the rest.
