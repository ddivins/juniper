# juniper

Juniper-focused scripts and tooling -- anything from automation that runs
directly on a Junos device to analysis tooling that runs on a workstation
against data Juniper publishes.

Organized by where each thing runs:

- [`on-box/`](on-box/) -- Junos op scripts, event scripts, and commit
  scripts. These run on the device itself, connect via the box's own local
  NETCONF session, and (for event/commit scripts) can make configuration
  changes.
- [`off-box/`](off-box/) -- tooling that runs on a workstation. No
  connection to a device, no configuration changes.

## on-box

- [`on-box/dhcp-reservations`](on-box/dhcp-reservations/) -- converts
  active DHCP server lease bindings into static DHCP reservations.
- [`on-box/srx-if-stats`](on-box/srx-if-stats/) -- read-only op script
  reporting per-interface bandwidth/drops plus flow session and SPU
  CPU/memory stats.
- [`on-box/clear-sessions-by-prefix`](on-box/clear-sessions-by-prefix/) --
  clears active flow sessions for a configurable list of IPv4/IPv6
  destination prefixes.

## off-box

- [`off-box/jnpr-trap-analysis`](off-box/jnpr-trap-analysis/) -- builds a
  searchable catalog of every SNMP trap a Junos or Junos-EVO release can
  send, with varbind values decoded from their MIB definitions and
  release-to-release/OS-to-OS comparison.
