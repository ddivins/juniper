# ber-remediation

Two on-box Python event scripts for Junos and Junos EVO that take a link
with a sustained high bit-error rate out of its aggregated-Ethernet (AE)
bundle, but only when it is safe to do so.

| Script | Job |
|---|---|
| [`ber_monitor.py`](ber_monitor.py) | Runs every minute, measures the framing-error rate on a list of interfaces, and raises a `HIGH BER` syslog alarm when an interface stays above the threshold. |
| [`ber_remediate.py`](ber_remediate.py) | Triggered by that alarm. Checks the backup path and the bundle's remaining members, then disables the link and removes it from the bundle. |

Tested on PTX10001-36MR, Junos EVO 24.4R2-S5.4, with live traffic (see
[Lab tests](#lab-tests)). The scripts choose `ether-options` (EVO) or
`gigether-options` (Junos) from the interface's own configuration; the
Junos branch has not been lab-tested.

## How it works

```
generate-event (60 s)
      │
      ▼
ber_monitor.py ── breach 1, 2 ──▶ syslog: BER-SAMPLE breach n/3 on <ifd>      (notice)
      │
      └─ breach 3, 4, … ────────▶ syslog: HIGH BER (via framing-errors): <ifd> (warning)
                                        │
                     event policy matches "HIGH BER.*"
                                        ▼
                                 ber_remediate.py ──▶ checks ──▶ commit
```

### Detection (`ber_monitor.py`)

On each run, for each interface:

```
allowed errors/s = input bits/s × threshold
breach           = input bits/s > 0  and  framing errors/s >= allowed errors/s
```

- Breaches are counted **per interface**. The alarm is logged from the
  `sustain`th consecutive breach onward, and again on every further
  breaching run, so a refused or failed removal is retried a minute later.
- A run without a breach resets the count.
- The first run for an interface only records a baseline. So does a run
  after a gap of more than 3 × `interval`, or one that finds a counter has
  gone backwards (`clear interfaces statistics`).
- An interface with no input traffic never breaches.

### Remediation (`ber_remediate.py`)

Checks run in this order. A failed check is logged and nothing is changed.

1. **Member.** The interface is an 802.3ad member and is not already
   disabled or removed.
2. **Backup path.** If `backup-unit` is set, that unit must be up with at
   least `backup-min-nbrs` OSPF neighbors. If it is not, the result depends
   on `backup-down-min-remaining`:
   - `-1` (default): refuse.
   - `N`: carry on, but check 4 then requires `N` (at least 1) active
     members to remain, whatever `min-remaining` says.
3. **Own bundle** (only with `require-own-ospf yes`). `<ae>.<ae-unit>` must
   be up with at least `min-ospf-nbrs` OSPF neighbors.
4. **Remaining members.** If the link is an active member, removing it must
   leave at least `min-remaining` active members, and never fewer than the
   bundle's `minimum-links`. `min-remaining 0` turns this check off while
   the backup is healthy, so the last member can be removed and traffic
   fails over to the backup. A member that is not active carries no traffic
   and is always removable.

"Active" means LACP collecting and distributing. In a bundle without LACP
it means the member link is up.

The change is made in a private candidate and committed with the comment
`<ifd> disabled and removed from <ae> (sustained high BER)`:

```
set interfaces <ifd> disable
deactivate interfaces <ifd> ether-options 802.3ad
```

Runs are serialized with a lock file. If two members of one bundle alarm in
the same minute, the second is judged after the first has been removed.

**Restoring a link is manual:**

```
delete interfaces <ifd> disable
activate interfaces <ifd> ether-options 802.3ad
```

### What happens in each situation

With `min-remaining 0` and `backup-down-min-remaining 1`, as in the example
config:

| Backup path | Active members in the bundle | Result |
|---|---|---|
| Up | 2 or more | Bad link removed |
| Up | 1 (the bad link) | Bad link removed; the bundle goes down and traffic moves to the backup |
| Down | 2 or more | Bad link removed |
| Down | 1 (the bad link) | Refused: there is nowhere for the traffic to go |

Removing a link reduces the bundle's capacity. With the backup down there is
no failover path, so a bundle that is more than (N−1)/N full will swap
errored packets for congestion drops. Use a larger
`backup-down-min-remaining`, or leave it at `-1`, if that matters more than
the errors.

## Arguments

### `ber_monitor.py`

| Argument | Default | Meaning |
|---|---|---|
| `interfaces` | *(required)* | Comma-separated physical interfaces, e.g. `et-0/0/5,et-0/0/6` |
| `threshold` | `1e-7` | Bit-error ratio: framing errors per input bit. `0` makes every run with traffic a breach; use it only to test the alarm path in a lab. |
| `sustain` | `3` | Consecutive breaching runs before `HIGH BER` |
| `interval` | `60` | Seconds between runs. Must match the `generate-event time-interval`. |

### `ber_remediate.py`

| Argument | Default | Meaning |
|---|---|---|
| `message` | *(required)* | `"{$$.message}"`, the text of the alarm |
| `backup-unit` | *(empty)* | Backup logical unit, e.g. `ae10.0`. Empty skips check 2. |
| `backup-min-nbrs` | `1` | OSPF neighbors required on `backup-unit` |
| `backup-down-min-remaining` | `-1` | What to do when the backup is down; see check 2 |
| `require-own-ospf` | `no` | `yes` turns on check 3 |
| `ae-unit` | `0` | Unit of the member's own bundle used by check 3 |
| `min-ospf-nbrs` | `1` | OSPF neighbors required by check 3 |
| `ospf-instance` | *(empty = master)* | Routing instance OSPF runs in. **Set it when OSPF is in a routing instance**; without it no neighbors are found and every removal is refused. |
| `min-remaining` | `1` | Active members that must remain; see check 4 |

## Install

1. Copy both scripts to the device. Use the exact file names; the event
   policy refers to them.

   ```
   scp ber_monitor.py ber_remediate.py user@device:/var/db/scripts/event/
   ```

2. Get the checksums on the device:

   ```
   file checksum sha-256 /var/db/scripts/event/ber_monitor.py
   file checksum sha-256 /var/db/scripts/event/ber_remediate.py
   ```

3. Load [`event-options.example.set`](event-options.example.set) after
   changing the interfaces, backup unit, OSPF instance, user name and the
   two checksums. The user needs permission to read interface and OSPF
   state and to commit configuration.

The state file (`/var/tmp/ber_monitor.json`) and lock files
(`/var/tmp/ber_monitor.lock`, `/var/tmp/ber_remediate.lock`) are created on
first run.

### Things that will stop it working

- **CRLF line endings break the checksum on EVO.** At commit, EVO hashes
  the file with carriage returns stripped; at run time it hashes the raw
  bytes. So no checksum value works for a script with CRLF endings: the
  raw-file hash is rejected at commit (`mustd: SHA-256 checksum value does
  not match`), and the stripped hash is accepted but the script is then
  blocked at run time (`EVENTD_SCRIPT_CHECKSUM_MISMATCH`). Keep the files
  LF-only. The
  [`.gitattributes`](.gitattributes) here enforces that for checkouts; check
  with `file ber_monitor.py`, which must not say "with CRLF line
  terminators".
- **`minimum-links` on the bundle blocks removing the last member.** EVO
  rejects the commit (`Number of member links configured, i.e [0], for
  interface [aeN] is lesser than the required minimum [1]`). The script
  logs `commit FAILED` and the bundle stays up on its last link.
- **OSPF in a routing instance needs `ospf-instance`.** See the arguments
  table.
- **Run one monitor policy.** Two policies running `ber_monitor.py` would
  share one state file and lock, and skip or corrupt each other's samples.

## Syslog messages

Both scripts log to facility `daemon` with the process tag `cscript`.

### `ber_monitor.py`

| Severity | Message |
|---|---|
| warning | `HIGH BER (via framing-errors): <ifd> has framing-errors=<r>/s, allowed=<a>/s over last <s>s (BER threshold <t>); Framing Error Delta=<n>, Input Bytes Delta=<n> (~<n> B/s), Bit-Errors-Sec Delta=<n>, Errored-Block-Sec Delta=<n>, bps=<n> [sustained <n>/<N> samples]` |
| notice | `BER-SAMPLE breach <n>/<N> on <ifd>: <same detail>` |
| notice | `BER-MONITOR: previous run still active; skipping` |
| error | `BER-MONITOR: interface <ifd> not found` |
| error | `BER-MONITOR: error reading <ifd>: <reason>` |
| error | `BER-MONITOR: <argument problem>; not running` |
| error | `BER-MONITOR: run failed: <reason>` |

### `ber_remediate.py`

Every line starts `BER-REMEDIATION: `. None contains `HIGH BER`, so the
script cannot trigger itself.

| Severity | Message |
|---|---|
| notice | `sustained high BER on <ifd> (member of <ae>); evaluating removal [ber_remediate <version>].` |
| notice | `backup <unit> up=<bool> ospf_nbrs=<n>: OK.` |
| notice | `backup <unit> up=<bool> ospf_nbrs=<n> (need >= <n>): DOWN; <ae> must keep >= <n> active member(s).` |
| notice | `<ifd> is not an active member of <ae> (active: [...]); remaining-member check not needed.` |
| notice | `<ifd> is NOT a member of an AE bundle; no action.` |
| notice | `<ifd> already disabled/removed from its bundle; nothing to do.` |
| **warning** | `<ifd> has been disabled and removed from <ae>; <n> active member(s) remain [...].` |
| **warning** | `<ifd> has been disabled and removed from <ae>; <n> active member(s) remain [...]; backup <unit> is DOWN.` |
| warning | `backup <unit> up=<bool> ospf_nbrs=<n> (need >= <n>); NOT removing <ifd>.` |
| warning | `<ae>.<unit> up=<bool> ospf_nbrs=<n> (need >= <n>); NOT removing <ifd>.` |
| warning | `removing <ifd> would leave <n> active member(s) in <ae> [...] (need >= <n>); NOT removing.` |
| warning | `backup <unit> is DOWN and removing <ifd> would leave <n> active member(s) in <ae> [...] (need >= <n>); NOT removing.` |
| error | `commit FAILED for <ifd>: <reason>` |
| error | `unexpected error handling <ifd>: <reason>` |
| error | `bad arguments; not running.` |

To alert on an action, match `has been disabled and removed from`. To alert
on a refusal, match `NOT removing`.

With `explicit-priority` the lines look like this:

```
cscript[21601]: %DAEMON-4: HIGH BER (via framing-errors): et-0/0/5 has framing-errors=0.00/s, ... [sustained 3/3 samples]
cscript[21773]: %DAEMON-5: BER-REMEDIATION: backup ae10.0 up=True ospf_nbrs=1: OK.
cscript[21773]: %DAEMON-4: BER-REMEDIATION: et-0/0/5 has been disabled and removed from ae12; 1 active member(s) remain ['et-0/0/6'].
```

## Testing it

**The whole chain, on one port.** Set the monitor to `threshold 0` and list
only that port. Every run with traffic then counts as a breach, so about
three minutes after the commit the port is removed:

```
set event-options policy BER_MONITOR then event-script ber_monitor.py arguments threshold 0
set event-options policy BER_MONITOR then event-script ber_monitor.py arguments interfaces et-0/0/5
```

Put `threshold` and `interfaces` back afterwards.

**Remediation only.** Inject the alarm from the shell. One message triggers
`ber_remediate.py` immediately:

```
logger -p daemon.warning "HIGH BER (via framing-errors): et-0/0/5 has TEST"
```

Both tests make a real configuration change if the checks pass.

## Lab tests

Two PTX10001-36MR back to back, Junos EVO 24.4R2-S5.4. `ae12` (2 × 100G,
LACP, OSPF cost 1) is the primary path and `ae10` (OSPF cost 100) the
backup, both in a `virtual-router` instance `VRF01`. A traffic generator on
a static bundle `ae11` sends about 98 Mbps each way across `ae12`. Syslog
was read from a remote server receiving `any info`.

Arguments: `backup-unit ae10.0`, `backup-down-min-remaining 1`,
`min-remaining 0`, `ospf-instance VRF01`.

| Case | Trigger | Result |
|---|---|---|
| Whole chain, backup up, 2 members | `threshold 0` on et-0/0/5 | `BER-SAMPLE` 1/3 and 2/3, `HIGH BER` 3/3, link removed 3 s later, 1 member remains |
| Backup up, last member | injected alarm | Removed; `ae12` down, route and traffic (~98 Mbps) moved to `ae10` |
| Backup down, 2 members | injected alarm | Removed; `... 1 active member(s) remain ['et-0/0/6']; backup ae10.0 is DOWN.` |
| Backup down, last member | injected alarm | Refused: `would leave 0 active member(s) in ae12 [] (need >= 1); NOT removing.` |
| Backup down, only member of static `ae11` | injected alarm | Refused, same message; confirms the non-LACP member lookup |
| Link already removed | injected alarm | `already disabled/removed from its bundle; nothing to do.` |
| Interface not in a bundle | injected alarm | `is NOT a member of an AE bundle; no action.` |
