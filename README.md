# juniper

Collection of on-box Juniper SRX automation scripts (op scripts, event
scripts, commit scripts).

## Scripts

- [`scripts/dhcp-reservations`](scripts/dhcp-reservations/) -- converts
  active DHCP server lease bindings into static DHCP reservations.
- [`scripts/srx-if-stats`](scripts/srx-if-stats/) -- read-only op script
  reporting per-interface bandwidth/drops plus flow session and SPU
  CPU/memory stats.
