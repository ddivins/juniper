# jnpr-trap-analysis

Off-box Python toolkit that turns Juniper's SNMP MIB text files into a
searchable catalog of every trap (`NOTIFICATION-TYPE`) a Junos or
Junos-EVO device can send -- name, OID, description, and each varbind's
enumerated values decoded from its `OBJECT-TYPE` definition (e.g. a BGP
peer-state varbind resolved to `1=idle, 2=connect, ... 6=established`,
not left as a bare integer).

It also tracks releases over time and across the two operating systems, so
you can answer things like "what traps changed between 25.4R1 and 26.2R1"
or "which traps exist on Junos but not on Junos-EVO" directly, instead of
diffing MIB files by hand.

Two outputs, both generated locally, neither committed to this repo (see
"Regenerating the outputs" below):

- `juniper_trap_catalog.xlsx` -- one row per trap, with per-release
  presence, lifecycle (added/removed/unchanged), and Junos-vs-Junos-EVO
  diff columns. Opens in Excel like any other spreadsheet.
- `juniper_trap_catalog.html` -- a standalone, self-contained page (open it
  directly in a browser, no server needed) with a searchable/filterable
  browse view and a release-to-release compare view, including across
  operating systems.

## Getting the MIBs

MIB files aren't included in this repo -- they carry Juniper's own
copyright notice, and this repo ships the tooling, not Juniper's
redistributable text. Download what you need from
[apps.juniper.net/mib-explorer](https://apps.juniper.net/mib-explorer/)
instead.

The two operating systems are packaged differently, which matters for how
you extract them:

**Junos** downloads as a `.zip` whose *internal* layout is already
`JuniperMibs/` and `StandardMibs/` at the top level -- there's no
wrapping version folder inside the archive. Create that folder yourself
and extract into it:

```
mkdir juniper-mibs-<version>
cd juniper-mibs-<version>
unzip /path/to/downloaded-file.zip
cd ..
```

**Junos-EVO** downloads as a `.tar.gz` with every `.txt` file directly at
the top level -- also no wrapping folder. Same approach:

```
mkdir junos-evo-mibs.<version>-EVO
cd junos-evo-mibs.<version>-EVO
tar xzf /path/to/downloaded-file.tar.gz
cd ..
```

Both end up living directly inside this `jnpr-trap-analysis/` directory,
next to the scripts. `.gitignore` already excludes both naming patterns,
so they won't accidentally get committed.

## Directory structure the scripts expect

```
jnpr-trap-analysis/
  build_full_catalog.py
  build_artifact.py
  parse_notifications.py
  parse_objects.py
  juniper-mibs-24.4R2/              <- Junos, one dir per release
    JuniperMibs/
      mib-jnx-chassis.txt
      ...
    StandardMibs/
      mib-bgpmib.txt
      ...
  juniper-mibs-25.4R1.12/
    JuniperMibs/
    StandardMibs/
  junos-evo-mibs.24.4R2-EVO/        <- Junos-EVO, one dir per release
    jnx-chassis.txt                 (flat -- no subdirectories)
    bgpmib.txt
    ...
```

The version string in the catalog is exactly whatever follows
`juniper-mibs-` or `junos-evo-mibs.` in the directory name -- name the
directory the way you want the release to read (e.g.
`juniper-mibs-26.2R1.7` shows up as `26.2R1.7`).

Load as many or as few releases as you want, in either OS -- one Junos
directory alone works fine, so does a mix of several Junos and several
Junos-EVO releases. Only directories matching one of the two naming
patterns above are picked up; everything else in this folder (README,
`.gitignore`, `*.zip`/`*.tar.gz` you haven't extracted yet) is ignored.

## Running it

```
pip3 install openpyxl      # once
python3 build_full_catalog.py
python3 build_artifact.py
```

`build_full_catalog.py` does the actual MIB parsing and writes
`juniper_notifications_full.json` (the intermediate data) plus
`juniper_trap_catalog.xlsx`. `build_artifact.py` reads that JSON and
renders `juniper_trap_catalog.html` -- run it second, after the JSON
exists.

Both scripts locate everything relative to their own location, so `cd`
into `jnpr-trap-analysis/` first and run them from there.

### Adding a new release later

Extract the new directory into this folder following the naming
convention above, then re-run both commands. No code changes needed --
`build_full_catalog.py` re-discovers every `juniper-mibs-*` and
`junos-evo-mibs.*` directory each time it runs.

### Scope: enterprise-only vs. `--include-standard`

By default, only Juniper-authored MIB files (the `jnx-`/`mib-jnx-`
prefixed ones) are scanned for `NOTIFICATION-TYPE` definitions -- roughly
500 Juniper-enterprise traps per Junos release. The dependency MIBs
Juniper ships alongside them (real BGP4-MIB, OSPF, PIM, MSDP, PCEP, LLDP,
RMON, and others) are still used to resolve varbind enum values, but
their own ~145-per-release worth of standards-track traps aren't included
in the catalog unless asked for:

```
python3 build_full_catalog.py --include-standard
python3 build_artifact.py
```

### Regenerating the outputs

Neither `juniper_trap_catalog.xlsx` nor `juniper_trap_catalog.html` (nor
the intermediate `juniper_notifications_full.json`) is committed to this
repo -- they're fully reproducible from the two commands above, and
committing a snapshot just means it goes stale the next time a MIB
release is added. Run the two commands whenever you want current output.

## What each script does

- `parse_notifications.py` -- library module. Extracts every
  `NOTIFICATION-TYPE` from a single MIB file: name, OID, `STATUS`,
  `DESCRIPTION`, and its `OBJECTS` (varbind) list.
- `parse_objects.py` -- library module. Extracts every `OBJECT-TYPE` and
  `TEXTUAL-CONVENTION` from a single MIB file, and resolves enumerated
  `INTEGER`/`BITS` `SYNTAX` values -- either declared inline or via a
  named textual convention (chasing the chain, e.g. an object whose
  `SYNTAX` is `TruthValue` resolves through `SNMPv2-TC`'s definition of
  `TruthValue` to `1=true, 2=false`).
- `build_full_catalog.py` -- orchestrator. Discovers releases, parses
  every MIB file in each (notifications scoped per `--include-standard`,
  the object/TC index always scanned in full since Juniper's own objects
  routinely reference standard conventions), cross-references varbinds
  against resolved enums, and unions everything into one registry keyed
  by trap name with a presence snapshot per release. Writes the JSON and
  the xlsx.
- `build_artifact.py` -- reads the JSON and renders the standalone HTML
  catalog. Doesn't touch the MIB files itself.

## Notes

- A trap's identity across releases is its bare name (e.g.
  `jnxBgpM2Established`). If Juniper ever renames a trap outright between
  releases, it shows up as one trap "removed" and an unrelated one
  "added" rather than a rename -- worth a manual look if a comparison
  ever turns up something that doesn't make sense.
- Junos-EVO defines far fewer traps than Junos even within the same
  enterprise scope (roughly 220-230 vs. 520-530) -- largely because whole
  Junos MIB categories (ATM, most SRX security/flow/policy/IDP/screening
  modules, IPsec monitoring, fabric-chassis) don't apply to the hardware
  and feature set EVO targets. That's an expected platform difference,
  not a parsing gap.
- Neither script modifies or touches a live device -- both operate
  entirely on local MIB text files. This is the "off-box" half of the
  repo for exactly that reason: nothing here runs on, or connects to, a
  Junos box.
