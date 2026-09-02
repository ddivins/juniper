# off-box

Tooling that runs on a workstation, not on a Junos device -- no NETCONF
connection to a box, no configuration changes, nothing to install on-device.
Currently that means working with data Juniper publishes (MIBs), rather
than connecting to any hardware.

- [`jnpr-trap-analysis`](jnpr-trap-analysis/) -- builds a searchable
  catalog of every SNMP trap a Junos or Junos-EVO release can send, with
  varbind values decoded and release-to-release/OS-to-OS comparison.

See [`../on-box`](../on-box/) for scripts that run on the device itself.
