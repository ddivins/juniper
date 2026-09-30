# off-box

Tooling that runs on a workstation, not on a Junos device -- nothing to
install on-device and no configuration changes. Most of it works with data
Juniper publishes (MIBs, IDP signature packs) rather than connecting to
hardware; where a tool can optionally open a read-only session to a device,
its README says so.

- [`jnpr-trap-analysis`](jnpr-trap-analysis/) -- builds a searchable
  catalog of every SNMP trap a Junos or Junos-EVO release can send, with
  varbind values decoded and release-to-release/OS-to-OS comparison.
- [`srx-idp`](srx-idp/) -- SRX IDP signature tooling: signature delta
  reports against Juniper's signature database, update-pack download and
  offline manifest comparison, and export of a device's attack list.

See [`../on-box`](../on-box/) for scripts that run on the device itself.
