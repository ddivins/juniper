# juniper

Collection of on-box Juniper SRX automation scripts (op scripts, event
scripts, commit scripts).

## Scripts

- [`scripts/dhcp-reservations`](scripts/dhcp-reservations/) -- converts
  active DHCP server lease bindings into static DHCP reservations.
- [`scripts/srx-if-stats`](scripts/srx-if-stats/) -- read-only op script
  reporting per-interface bandwidth/drops plus flow session and SPU
  CPU/memory stats.
- [`scripts/clear-sessions-by-prefix`](scripts/clear-sessions-by-prefix/) --
  clears active flow sessions for a configurable list of IPv4/IPv6
  destination prefixes.
