# le-ca-sync

On-box Junos Python event script that keeps a device's local PKI trust
store in sync with whatever Let's Encrypt is *actually* issuing from,
so an `auto-re-enrollment acme` certificate doesn't silently break the
next time Let's Encrypt rotates its intermediate/root hierarchy.

Verified end-to-end against a real SRX1600 (25.4R1-S2.3): an
`ACME-RA-CERT` certificate had renewed under Let's Encrypt's new
"Gen Y" hierarchy (`YR2`, chaining to a brand-new `Root YR` -- not
cross-signed under the previously-trusted `ISRG Root X1` the way past
LE rotations were), leaving `Cert-Chain: Issuer CA Certificate Missing`
and the `auto-re-enrollment ... ca-profile-name` stanza pointed at a
dead `R12` profile Let's Encrypt had stopped issuing from. One run of
this script, fired against that live broken state: created
`LE_INT_YE1`/`LE_INT_YE2`/`LE_INT_YR1`/`LE_INT_YR2` ca-profiles, loaded
the actual current certs into them, added them to `trusted-ca-group
LE`, and repointed `ca-profile-name` to `LE_INT_YR2` -- `Cert-Chain`
went from `Issuer CA Certificate Missing` to `YR2`. Confirmed
idempotent on rerun (no "already exists" errors, no-ops when nothing's
changed) and as an unattended event-script firing on a timer,
including two real autonomous daily firings (not manually triggered)
that each found nothing to change and correctly no-op'd. A later fix
(see "Why the page-boundary regex matters" below) corrected a bug
where root certs were being silently skipped -- confirmed against the
live page, which added 7 previously-missing profiles in one run with
no disruption to the already-working chain.

## What it actually does, each run

1. Fetches the current-certificates section of
   [`letsencrypt.org/certificates`](https://letsencrypt.org/certificates/)
   (everything before the first collapsed `Backup`/`Retired`/`Expired`
   section -- see "Why the page-boundary regex matters" below) and
   pulls every `.pem` link out of it -- roots and intermediates alike,
   whatever Let's Encrypt is currently issuing from, by name.
2. Diffs those against the ca-profiles already configured. For
   anything missing, creates a `ca-profile` (named `LE_<PEM
   BASENAME>`), downloads the actual certificate, loads it, and adds
   the profile to `trusted-ca-group LE`.
3. Reads back **every** relevant profile's real Subject CN (old ones
   too, not just new), compares that against `ACME-RA-CERT`'s actual
   current issuer CN, and repoints
   `auto-re-enrollment acme certificate-id ACME-RA-CERT ca-profile-name`
   to whichever profile's CN actually matches -- by fact, not by
   assuming a specific intermediate name will stay correct.

It only *adds* trust -- it never removes a ca-profile or drops
anything from `trusted-ca-group LE`. Retiring old profiles (e.g. a
dead `R12`/`R13` from a previous hierarchy) is a separate, deliberate
cleanup step, not something this script does automatically.

## Copying the files

Two files need to land on the box -- the script itself, and its CA
bundle (see "The CA bundle" below):

```
scp le_ca_sync.py user@device:/var/db/scripts/event/le_ca_sync.py
scp cacert.pem user@device:/var/home/<user>/cacert.pem
```

`file copy` (Junos's own CLI download command) does not work when
invoked over NETCONF -- see "Why urllib instead of `file copy`" below
-- so unlike some other scripts in this repo, `scp`/`sftp` from a
workstation is the only way to get files onto the box for this one;
the script can't fetch its own dependencies via the CLI.

After `scp`, the script needs its executable bit set (`scp` alone
leaves it `-rw-r--r--`, which was not enough in testing -- unlike some
other on-box scripts here, this one failed without `chmod`):

```
sftp user@device
sftp> chmod 755 /var/db/scripts/event/le_ca_sync.py
sftp> bye
```

## Required configuration (one block)

```
# 1. Enable Python for on-box scripts.
set system scripts language python3

# 2. Register as an event script, and grant it a real user's access
#    privileges (see "Why python-script-user is required" below).
#    <login-user> must be able to configure [edit security pki] and
#    [edit event-options] -- reusing an existing admin account is
#    simplest, same trade-off as discussed in ../dhcp-reservations.
set event-options event-script file le_ca_sync.py python-script-user <login-user>

# 3. Trigger it on a timer. This is a reconciliation job, not tied to
#    a specific syslog message -- 86400 = once a day, comfortably
#    inside the `re-enroll-time days N` window on any ACME
#    certificate-id, so a hierarchy change is caught well before the
#    box would otherwise need it.
set event-options generate-event LE_CA_SYNC_DAILY time-interval 86400
set event-options policy LE_CA_SYNC_POLICY events LE_CA_SYNC_DAILY
set event-options policy LE_CA_SYNC_POLICY then event-script le_ca_sync.py

commit
```

Verified working example, straight from a tested box:

```
set system scripts language python3
set event-options event-script file le_ca_sync.py python-script-user claude
set event-options generate-event LE_CA_SYNC_DAILY time-interval 86400
set event-options policy LE_CA_SYNC_POLICY events LE_CA_SYNC_DAILY
set event-options policy LE_CA_SYNC_POLICY then event-script le_ca_sync.py
commit
```

**`WORKDIR` and `CA_BUNDLE` in [`le_ca_sync.py`](le_ca_sync.py) are
hardcoded to `/var/home/claude`** -- the home directory of the
`python-script-user` on the box this was verified against. Change both
constants to match whatever `<login-user>` actually is in your
deployment before copying the script over; they don't self-detect.

This script has no analog of `dry-run` (unlike `dhcp-reservations`) --
every run either does nothing (nothing new to trust, nothing to
repoint) or commits real config. There's no destructive branch to
preview: it only ever adds ca-profiles/trusted-ca-group members and,
at most, repoints one `ca-profile-name` value.

## The CA bundle

[`cacert.pem`](cacert.pem) is Mozilla's curated CA bundle (the same one
curl/many HTTP clients ship by default), fetched from
**https://curl.se/ca/cacert.pem**. The script needs it because it does
its own HTTPS fetching in Python (see below) rather than going through
Junos's own download mechanism, and Python's default SSL context has
no trust store wired in on this platform -- without it, every fetch
fails with `SSLCertVerificationError: unable to get local issuer
certificate`.

Ship this file alongside the script (as above) rather than relying on
the fallback: if `CA_BUNDLE` is missing on a run, the script *will*
bootstrap it by downloading `CA_BUNDLE_URL` itself and logging a loud
`external.warn` syslog line -- but that one bootstrap fetch is
necessarily **unverified** (there's nothing to verify a CA bundle
against before you have one), so it's a deliberately narrow, logged,
last-resort fallback, not the intended normal path. Re-fetching it
periodically (say, whenever you touch this deployment) isn't a bad
idea either way -- Mozilla's list does change over time.

## Why urllib instead of `file copy`

Confirmed directly, twice: `file copy <url> <dest>` returns
successfully (no RPC error, no exception) when invoked over NETCONF --
via this script's own `Device()` connection, and separately via a
Junos MCP server issuing the identical command -- but **does not
actually create the destination file**. It only works from a real
interactive CLI/PTY session (the progress-bar/percentage display isn't
cosmetic -- it's load-bearing for the command to function at all).
Since an event script's only connection to the box is NETCONF, `file
copy` is a dead end here regardless of syntax.

The fix is to not route HTTP fetches through the Junos CLI at all:
`le_ca_sync.py` uses Python's own `urllib.request` (with the CA bundle
above for verification) to fetch both the certificates page and every
individual `.pem`, writing them straight to local disk with a plain
`open(path, "wb")` -- no CLI/RPC layer involved in the download at
all. Loading a fetched cert into the PKI store afterward (`request
security pki ca-certificate load ...`) is a normal one-shot `request`
command, not an interactive/progress one, and works fine over NETCONF
-- only `file copy` itself is broken this way.

## Why the page-boundary regex matters

`letsencrypt.org/certificates` has **no literal "Active" heading** --
an earlier version of this script scraped for the word "Active"
case-insensitively, on the assumption the page had a section by that
name. It doesn't. The real boundaries are the collapsed
`<summary>Backup</summary>` / `<summary>Retired</summary>` /
`<summary>Expired</summary>` elements; everything before the first one
is implicitly current, with no heading of its own.

That old regex didn't error, which is what made it dangerous: the word
"active" *does* appear on the page, lowercase, mid-sentence ("We
currently maintain four intermediates in active rotation") -- and that
sentence happens to sit right before the four intermediates but
**after** every root cert (`isrgrootx1.pem`, `isrg-root-x2.pem`,
`root-yr.pem`, `root-yr-by-x1.pem`, etc.). So the old script quietly
matched the four intermediates every single run, never raised a
warning, and never once loaded a root cert -- discovered only by
manually diffing the box's configured ca-profiles against the page's
raw HTML, since nothing about the successful, idempotent daily runs
gave any indication something was being silently skipped.

`active_cert_hrefs()` now anchors on the real boundary instead:

```python
m = re.search(r'(.*?)<summary>\s*(?:Backup|Retired|Expired|Not Yet in Trust Stores)\s*</summary>', html, re.S | re.I)
```

Confirmed with a fresh run against the live page: this picked up 7
previously-missing profiles in one pass (`LE_ISRGROOTX1`,
`LE_ISRG_ROOT_X2`, `LE_ROOT_X2_BY_X1`, `LE_ROOT_YE`,
`LE_ROOT_YE_BY_X2`, `LE_ROOT_YR_BY_X1`, `LE_ISRG_ROOT_X1_CROSS_SIGNED`),
each with the enrollment URL set and added to `trusted-ca-group LE`,
with zero effect on the already-trusted current cert chain.

Also worth knowing: Let's Encrypt has since added a third intermediate
per key type (`int-ye3.pem`, `int-yr3.pem`) -- but as of this writing
those sit inside the `Backup` section, not the current one, so they're
correctly excluded. If Let's Encrypt ever promotes them to active
issuance, this script picks them up automatically; no code change
needed.

## Why `python-script-user` is required

Same root cause as [`../dhcp-reservations`](../dhcp-reservations/):
Junos runs an eventd-triggered script as the unprivileged OS user
`nobody` unless `python-script-user <user>` is set on the
`event-script file` stanza, and `nobody` can't open the script's own
local `Device()` connection (`ConnectError: user "nobody" does not
have access privileges`). See that script's README for the full
explanation -- it applies here unchanged.

One extra wrinkle found specifically while debugging *this* script:
`Junos_Context` on this platform (25.4R1-S2.3) has **no** `device` or
`connection` key at all -- just metadata (`hostname`, `pid`,
`script-type`, `user-context`, etc.). `Junos_Context["device"]` raises
a plain `KeyError`, not a permissions error. The fix either way is the
same `Device()`-with-empty-args pattern PyEZ provides for local
connections; `Junos_Context` was never the right place to look for a
connection handle on this release.

## Testing

Event-script output goes to syslog (tagged `le_ca_sync`), not to a
terminal -- check with:

```
show log messages | match le_ca_sync
```

Every `cli()` call this script makes is logged there too (command plus
a truncated snippet of its output), which is what actually made this
script possible to debug -- `show log escript.log` shows *whether* a
run succeeded or raised, but silent logic bugs (wrong regex, a
condition that just never triggers) don't show up as a traceback at
all. If you trim this logging down for a quieter production box, keep
enough of it to answer "did the repoint condition actually get
evaluated, and against what values" without needing another debug
cycle.

To force a run without waiting for the daily timer, temporarily drop
the interval and put it back once you've confirmed the result:

```
set event-options generate-event LE_CA_SYNC_DAILY time-interval 60
commit
# wait ~70s, check results
set event-options generate-event LE_CA_SYNC_DAILY time-interval 86400
commit
```

A synthetic `generate-event` fires on its own timer from `eventd` --
manually logging a matching string with `logger` (e.g. `logger -p
local0.info "LE_CA_SYNC_DAILY"`) does **not** trigger it; confirmed
directly, it just writes a look-alike syslog line while the real event
script never runs.

## Troubleshooting

Start with syslog, tagged `le_ca_sync` (script's own logging) and
`escript.log` (Junos's own event-script execution log, including
Python tracebacks):

```
show log messages | match le_ca_sync
show log escript.log
```

**`ConnectError(... user "nobody" does not have access
privileges)`.** Missing `python-script-user` on the `event-script
file` stanza -- see "Why python-script-user is required" above.

**`KeyError: 'device'` from `Junos_Context["device"]`.** You're
looking at (or copied from) example code written against a different
Junos release/API assumption. This script uses `Device()` with an
empty argument list instead -- see above.

**`RpcError(... bad_element: display, message: syntax error)`.** A
command sent through `dev.cli()` (or any NETCONF `<command>` RPC) had
a `| display set`, `| match`, or similar pipe modifier on it. Those
only work in a real interactive CLI session; over RPC, send the plain
`show`/`request` command and parse the normal (curly-brace)
configuration text in Python instead.

**`SSLCertVerificationError: unable to get local issuer
certificate`.** The CA bundle (`CA_BUNDLE` in the script) is missing
or the path doesn't match where you actually copied it -- see "The CA
bundle" above.

**`Command aborted as CA certificate already exists. Retry after
clearing the existing CA certificate`.** The script tried to
`request security pki ca-certificate load` into a profile that already
has a certificate loaded -- normal Junos PKI behavior, not something to
work around by force-reloading. `le_ca_sync.py` already guards against
this (it only loads into profiles that are new *this run*); if you're
seeing it anyway, something upstream of that check regressed --
confirm `existing_ca_profiles()` is actually finding the profile (its
regex expects the plain curly-brace `show configuration security pki`
format, not `| display set`).

**Certificates load and profiles get created, but
`ca-profile-name` never repoints.** Check that `cn_of()` and
`current_leaf_issuer_cn()` are actually returning a CN and not
`None` -- their regexes need `re.S` (`DOTALL`) because `Issuer:`/
`Subject:` and the `Common name:` that identifies them sit on
*separate lines* in `show security pki ... detail` output; a same-line
regex silently matches nothing (no exception, no error -- the repoint
condition just never evaluates true) rather than failing loudly. The
per-command syslog trail (see "Testing" above) shows exactly what each
`show` command actually returned, which is how this was caught.

**`CSCRIPT_SECURITY_WARNING: unsigned python script ... without
checksum is executed`.** Expected, shows up on every run, not an
error.

**Runs succeed, no errors anywhere, but some root certs never show up
as ca-profiles.** This was a real bug, not a hypothetical -- see "Why
the page-boundary regex matters" above. If you're running a version of
this script older than that fix, the symptom is exactly this: clean
`return: 0` on every run, no warning logged, `trusted-ca-group LE`
looks reasonable, and yet a byte-for-byte diff against
`letsencrypt.org/certificates`'s actual HTML shows roots missing. The
lesson generalized: a script that depends on scraping a web page's
prose should verify against the page's real markup once, by hand, not
just against whatever a summarized/rendered description of the page
implies its structure to be -- a clean run and an absence of logged
warnings are not the same thing as "found everything it should have."
