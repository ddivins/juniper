# on-box

Scripts that run directly on a Junos device -- op scripts, event scripts,
commit scripts. Each one connects to the box's own local NETCONF session
(or, for op scripts, is invoked straight from the CLI) and lives under
`/var/db/scripts/` on the device itself.

- [`dhcp-reservations`](dhcp-reservations/) -- converts active DHCP server
  lease bindings into static DHCP reservations.
- [`srx-if-stats`](srx-if-stats/) -- read-only op script reporting
  per-interface bandwidth/drops plus flow session and SPU CPU/memory
  stats.
- [`clear-sessions-by-prefix`](clear-sessions-by-prefix/) -- clears active
  flow sessions for a configurable list of IPv4/IPv6 destination
  prefixes.
- [`le-ca-sync`](le-ca-sync/) -- keeps a device's local PKI trust store
  in sync with whatever Let's Encrypt is actively issuing from, so an
  `auto-re-enrollment acme` certificate doesn't break the next time
  Let's Encrypt rotates its intermediate/root hierarchy.

See [`../off-box`](../off-box/) for tooling that runs on a workstation
instead of on the device.
