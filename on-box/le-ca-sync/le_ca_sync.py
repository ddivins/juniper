import os
import re
import ssl
import urllib.request

import jcs
from jnpr.junos import Device
from jnpr.junos.utils.config import Config

LE_CERTS_PAGE = "https://letsencrypt.org/certificates/"
CA_BUNDLE = "/var/home/claude/cacert.pem"
CA_BUNDLE_URL = "https://curl.se/ca/cacert.pem"
WORKDIR = "/var/home/claude"
TRUSTED_GROUP = "LE"
ACME_CERT_ID = "ACME-RA-CERT"

_ssl_ctx = None


def ssl_ctx():
    """Lazily build the verified SSL context, bootstrapping the CA bundle on first run if it's missing.

    Prefer shipping CA_BUNDLE alongside this script (from CA_BUNDLE_URL) at deploy time -
    the bootstrap fetch below is unverified (nothing to verify it against yet), so it's a
    deliberately narrow, logged, one-time fallback rather than the normal path.
    """
    global _ssl_ctx
    if _ssl_ctx is not None:
        return _ssl_ctx
    if not os.path.exists(CA_BUNDLE):
        jcs.syslog("external.warn", "le_ca_sync: %s missing, bootstrapping via UNVERIFIED fetch from %s" % (CA_BUNDLE, CA_BUNDLE_URL))
        with urllib.request.urlopen(CA_BUNDLE_URL, timeout=30, context=ssl._create_unverified_context()) as resp:
            data = resp.read()
        with open(CA_BUNDLE, "wb") as f:
            f.write(data)
        jcs.syslog("external.warn", "le_ca_sync: bootstrapped CA bundle (%d bytes) - verify integrity out-of-band" % len(data))
    _ssl_ctx = ssl.create_default_context(cafile=CA_BUNDLE)
    return _ssl_ctx


def fetch(url):
    """Fetch a URL directly in Python (file copy doesn't work over the NETCONF RPC path this script runs under)."""
    with urllib.request.urlopen(url, timeout=30, context=ssl_ctx()) as resp:
        return resp.read()


def cli(dev, command):
    """Run a literal operational-mode CLI command on-box and return its text output."""
    out = dev.cli(command, warning=False)
    jcs.syslog("external.info", "le_ca_sync: %s -> %r" % (command, out[:200]))
    return out


def load_config(dev, set_lines, comment):
    if not set_lines:
        return
    cu = Config(dev)
    cu.load("\n".join(set_lines), format="set", merge=True)
    cu.commit(comment=comment)


def existing_ca_profiles(dev):
    out = cli(dev, "show configuration security pki")
    return set(re.findall(r'^\s*ca-profile\s+(\S+)\s*\{', out, re.M))


def active_cert_hrefs():
    # The page has no literal "Active" heading - current certs are just whatever appears
    # before the first collapsed <summary>Backup/Retired/Expired</summary> section. Anchoring
    # on the real structural boundary here, not page prose (a prior version searched for the
    # word "Active" case-insensitively, which only occurs in unrelated sentences like "...in
    # active rotation..." that sit AFTER the root certs but before the intermediates - so it
    # silently captured only the 4 intermediates and never the roots).
    html = fetch(LE_CERTS_PAGE).decode("utf-8", errors="ignore")
    m = re.search(r'(.*?)<summary>\s*(?:Backup|Retired|Expired|Not Yet in Trust Stores)\s*</summary>', html, re.S | re.I)
    if not m:
        jcs.syslog("external.warn", "le_ca_sync: could not find a Backup/Retired/Expired boundary on certificates page")
        return []
    return sorted(set(re.findall(r'href="(/certs/[^"]+\.pem)"', m.group(1))))


def profile_name_for(href):
    base = href.rsplit("/", 1)[-1].replace(".pem", "")
    base = re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_').upper()
    return "LE_" + base


def cn_of(dev, profile):
    out = cli(dev, "show security pki ca-certificate detail ca-profile %s" % profile)
    m = re.search(r'Subject:.*?Common name:\s*([^\r\n,]+)', out, re.S)
    return m.group(1).strip() if m else None


def current_leaf_issuer_cn(dev):
    out = cli(dev, "show security pki local-certificate detail certificate-id %s" % ACME_CERT_ID)
    m = re.search(r'Issuer:.*?Common name:\s*([^\r\n,]+)', out, re.S)
    return m.group(1).strip() if m else None


def current_ca_profile_name(dev):
    out = cli(dev, "show configuration security pki auto-re-enrollment")
    m = re.search(r'ca-profile-name\s+(\S+);', out)
    return m.group(1) if m else None


def main():
    dev = Device()
    dev.open()
    try:
        known = existing_ca_profiles(dev)
        hrefs = active_cert_hrefs()

        new_set_lines = []
        new_profiles = set()
        cn_to_profile = {}
        local_paths = {}

        for href in hrefs:
            profile = profile_name_for(href)
            url = "https://letsencrypt.org" + href

            if profile not in known:
                new_profiles.add(profile)
                new_set_lines += [
                    "set security pki ca-profile %s ca-identity %s" % (profile, profile),
                    "set security pki ca-profile %s enrollment url https://acme-v02.api.letsencrypt.org/directory" % profile,
                    "set security pki ca-profile %s revocation-check disable" % profile,
                    "set security pki trusted-ca-group %s ca-profiles %s" % (TRUSTED_GROUP, profile),
                ]
                local_path = WORKDIR + "/" + href.rsplit("/", 1)[-1]
                local_paths[href] = local_path
                data = fetch(url)
                with open(local_path, "wb") as f:
                    f.write(data)

        if new_set_lines:
            load_config(dev, new_set_lines, "le_ca_sync: add new active Let's Encrypt CA profiles")

        # Only load the cert object for profiles that are new this run - Junos refuses to
        # re-load into a profile that already has a certificate. Still read every profile's
        # real Subject CN (old and new) so re-enrollment can be repointed by fact, not guesswork.
        for href in hrefs:
            profile = profile_name_for(href)
            if profile in new_profiles:
                cli(dev, "request security pki ca-certificate load ca-profile %s filename %s" % (profile, local_paths[href]))
            cn = cn_of(dev, profile)
            if cn:
                cn_to_profile[cn] = profile

        issuer_cn = current_leaf_issuer_cn(dev)
        wanted_profile = cn_to_profile.get(issuer_cn) if issuer_cn else None
        configured_profile = current_ca_profile_name(dev)

        if wanted_profile and wanted_profile != configured_profile:
            load_config(
                dev,
                ["set security pki auto-re-enrollment acme certificate-id %s ca-profile-name %s"
                 % (ACME_CERT_ID, wanted_profile)],
                "le_ca_sync: repoint %s to %s (issuer CN=%s)" % (ACME_CERT_ID, wanted_profile, issuer_cn),
            )
            jcs.syslog("external.info", "le_ca_sync: repointed %s ca-profile-name to %s" % (ACME_CERT_ID, wanted_profile))
    finally:
        dev.close()


if __name__ == "__main__":
    main()
