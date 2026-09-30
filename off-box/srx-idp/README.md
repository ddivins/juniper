# srx-idp

Off-box Python toolkit for working out what changed in Juniper SRX IDP
(intrusion detection/prevention) signature updates, and for turning that
into something you can act on -- a list of new signatures, a ready-to-paste
Junos attack group, or a diff of two raw update packs.

It runs on a workstation. **Connecting to a device is optional**: three of
the four commands only talk to Juniper's public signature servers or read
local files. Only `device-attacks` opens a session to an SRX.

## What it does

| Command | Question it answers | Network use |
|---|---|---|
| `spreadsheet` | "Which signatures are newer than the pack on my SRX, and what do I `set` to alert on them?" | Downloads Juniper's signature spreadsheet (or use your own copy) |
| `download` | "Get me the raw update packs so I can compare them." | Downloads from Juniper |
| `manifest` | "Which signature entries were added or changed between two update packs?" | None -- local files only |
| `device-attacks` | "What predefined attacks does this SRX have right now?" | SSH/NETCONF to an SRX |

The only link between the device and the rest is the **active pack number**.
Read it from the SRX (`show security idp security-package-version`) and pass
it to `spreadsheet`; nothing looks it up for you.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
cd off-box/srx-idp
uv sync
```

Commands below are run as `uv run srx-idp <command>`. Every command that
writes files takes `--output-dir` (default: the current directory).

## `spreadsheet` -- signature delta report

Compares Juniper's full signature database against the pack installed on
your SRX and reports everything newer.

```bash
uv run srx-idp spreadsheet 3741                      # download, then compare
uv run srx-idp spreadsheet 3741 --input signature.xlsx   # use a file you already have
```

`3741` is the update number of the pack currently active on the device. A
signature is included when its `signature_update_number` is greater than
that.

Without `--input`, the spreadsheet is downloaded from Juniper's signature
API to `signature.xlsx` in the output directory. The file is generated on
demand and can take a minute or more.

Outputs, where `<active>` is the pack number you supplied and `<latest>` is
the newest update number found in the spreadsheet:

- `sig_delta_report_<active>_<latest>.txt` -- a summary, Junos commands
  that (re)build a custom attack group named `SIG_DELTA`, and (with
  `--check-retired`) a `#`-commented list of retired signatures:

  ```
  Since active signature pack 3741 there are 21 new signatures
  Newest signature pack is 3762

  delete security idp custom-attack-group SIG_DELTA
  set security idp custom-attack-group SIG_DELTA group-members SCAN:MISC:IDP-TEST
  set security idp custom-attack-group SIG_DELTA group-members <signature name>
  ...
  ```

  `SCAN:MISC:IDP-TEST` is always present because a Junos attack group cannot
  be empty. Signature names are sorted and de-duplicated.
- `signature_delta_<active>_<latest>.xlsx` -- the matching rows from the
  spreadsheet with every original column, sorted by update number.

To use the group, reference it from an IDP rule, for example one that logs
but takes no action:

```
set security idp idp-policy <policy> rulebase-ips rule sig-delta match attacks custom-attack-groups SIG_DELTA
set security idp idp-policy <policy> rulebase-ips rule sig-delta then action no-action
set security idp idp-policy <policy> rulebase-ips rule sig-delta then notification log-attacks
set security idp idp-policy <policy> rulebase-ips rule sig-delta terminal
```

The group only reflects the delta at run time: applying the report deletes
and rebuilds it, so anything not in the list is removed from the group.

The spreadsheet must contain a `signatures` sheet with the columns
`signature_update_number`, `signature_name`, `signature_severity` and
`signature_release_date`; otherwise the command stops with a message naming
the missing columns. Rows with no update number are skipped.

### Installing a pack that isn't the newest: `--target-pack`

By default the delta runs up to the newest pack in the spreadsheet. If you
are installing a specific pack instead, cap the delta at it so every `set`
line refers to a signature that pack contains:

```bash
uv run srx-idp spreadsheet 3901 --target-pack 3930
```

The report header then reads "Target signature pack is 3930" and the files
are named `..._3901_3930`. The target must be greater than the active pack
and no newer than the newest pack in the spreadsheet.

### Retired signatures: `--check-retired`

The spreadsheet only lists signatures that currently exist -- retired ones
are simply absent, so the delta alone can never show them. `--check-retired`
finds them by comparing the two update packs and listing every entry that
is in the older pack but not the newer one:

```bash
uv run srx-idp spreadsheet 3901 --target-pack 3930 --check-retired
```

This downloads the active and target packs (about 60 MB each, to a temporary
directory that is deleted afterwards), or uses `latest` if you gave no
target. To avoid the download, supply both packs yourself with
`--old-pack` and `--new-pack` (see `download`). The platform options from
`download` (`--device`, `--os-version`, ...) apply here too.

With the packs in hand, the tool also checks the delta against the target
pack: a signature that is in the spreadsheet but not in that pack cannot be
added to `SIG_DELTA` on a device running it (the spreadsheet can keep a
signature the pack has already dropped or renamed). Those are left out of
the `set` commands and listed under `# Excluded from SIG_DELTA`, and the
delta workbook omits them too.

The retired list goes at the bottom of `sig_delta_report_*.txt`, every line
prefixed with `#` so the whole file can still be pasted into Junos. Use it
to find config that references signatures that no longer exist. Without the
flag, the report says `# Retired signatures: not checked`, so a missing
list is never mistaken for "none retired".

Retirements can differ by platform and Junos release, so the packs are
requested for the device/OS given by the platform options (default
`srxtvp`, 22.4). Set those to match your SRX.

### Original script syntax

The original single-file script is kept as a thin wrapper so existing muscle
memory and automation still work:

```bash
uv run python srx_idp_signature_delta_xls.py 3741           # download, then compare
uv run python srx_idp_signature_delta_xls.py 3741 offline   # use ./signature.xlsx
```

`offline` requires `signature.xlsx` in the current directory and does no
network access.

## `download` -- fetch update packs

Downloads full IDP update packs from Juniper's signature server, for use
with `manifest`.

```bash
uv run srx-idp download                  # the latest pack
uv run srx-idp download latest 3702      # latest plus pack 3702
```

Each argument is `latest` or a pack number. Packs are gzip-compressed on the
wire; the tool decompresses each one to `offline-update-<pack>` (for
example `offline-update-3702`, `offline-update-latest`) and deletes the
downloaded `.tgz`. Use `--keep-archive` to keep it.

The request mimics a device asking for an update, so its parameters default
to an `srxtvp` running Junos 22.4:

| Option | Default | Meaning |
|---|---|---|
| `--device` | `srxtvp` | Platform to request the pack for |
| `--os-version` | `22.4` | Junos release |
| `--build` | `3` | Junos build |
| `--detector` | `12.6.130180509` | IDP detector engine version |
| `--release` | `10` | Update release stream |
| `--serial` | `$SRX_SERIAL`, else omitted | Device serial number |

Set these to match the platform you care about. The serial is not sent
unless you provide it. If Juniper's server refuses requests without one,
export `SRX_SERIAL` (keep it out of version control).

## `manifest` -- compare two update packs

Reports which signature entries are new or changed between two update packs.
It reads local files only and never touches the network.

```bash
uv run srx-idp manifest offline-update-3702 offline-update-latest
```

Both files are the decompressed `SignatureUpdate` XML. The tool looks at
each `/SignatureUpdate/Entries/Entry`, keys it by its `Name`, canonicalizes
the XML (C14N) and flags every entry in the newer file that is missing from
the older one or whose canonical form differs. Output is the sorted list of
entry names followed by `Changed or added entries: <count>`.

Because the comparison is on canonical bytes, a change in element order
inside an entry counts as a change. Entries *removed* in the newer pack are
not reported.

Typical workflow:

```bash
uv run srx-idp download latest 3702
uv run srx-idp manifest offline-update-3702 offline-update-latest
```

## `device-attacks` -- export an SRX's attack list

The one command that connects to a device. It opens a NETCONF session over
SSH, reads the installed IDP security package version, pulls the recursive
`All Attacks` predefined group, and writes the sorted, de-duplicated list to
`idp_attack_list_<version>.txt`. Nothing is changed on the device.

Configure the connection with environment variables (copy `.env.example` to
`.env` and load it through your shell or IDE):

| Variable | Required | Meaning |
|---|---|---|
| `SRX_HOSTNAME` | yes | Device address |
| `SRX_USERNAME` | yes | Login user |
| `SRX_SSH_KEY` | one of these | Path to a private key (preferred; `~` is expanded) |
| `SRX_PASSWORD` | one of these | Password, used only if no key is set |
| `SRX_PORT` | no | SSH port, default `22` |

```bash
uv run srx-idp device-attacks
```

The command fails immediately with a clear message if the hostname, user or
credential is missing. Use a read-only account; the tool only issues
operational RPCs.

## Files this tool creates

All are generated locally and excluded by `.gitignore` -- they are large,
go stale quickly, and Juniper's signature data is not ours to redistribute.

| File | Created by |
|---|---|
| `signature.xlsx` | `spreadsheet` (download) |
| `sig_delta_report_<active>_<latest>.txt` | `spreadsheet` |
| `signature_delta_<active>_<latest>.xlsx` | `spreadsheet` |
| `offline-update-<pack>` | `download` |
| `idp_attack_list_<version>.txt` | `device-attacks` |

## Layout

```
off-box/srx-idp/
├── src/srx_idp/
│   ├── cli.py         argument parsing and command dispatch
│   ├── delta.py       spreadsheet download, delta selection, report writing
│   ├── download.py    update-pack URL building, download, gunzip
│   ├── manifest.py    SignatureUpdate XML loading and entry comparison
│   └── device.py      SRX connection settings and attack-list export
├── tests/             unit tests (no network or device needed)
├── srx_idp_signature_delta_xls.py   original script name, wraps delta.py
├── .env.example
└── pyproject.toml
```

## Tests

```bash
uv run python -m unittest discover -s tests -v
```

The tests mock all network access and never contact a device.

## Troubleshooting

- **`Missing required columns`** -- the spreadsheet layout changed or the
  file isn't Juniper's signature export. Re-download without `--input`.
- **`Offline mode requires .../signature.xlsx`** -- the wrapper script's
  `offline` mode only looks in the current directory.
- **HTTP error from `download` or `spreadsheet`** -- Juniper rejected or
  timed out the request. Retry; for `download`, check the platform options
  above and try supplying `--serial`.
- **`SRX_HOSTNAME and SRX_USERNAME are required`** -- `device-attacks` has no
  environment to read; see the table above.
