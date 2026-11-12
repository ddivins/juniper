#!/usr/bin/env python3
"""ber_remediate.py - Junos / Junos EVO event script: take a high-BER link out of its AE.

Triggered by an event policy that matches the alarm ber_monitor.py logs once
an interface has had a sustained high bit-error rate:

    HIGH BER (via framing-errors): <ifd> has ...

It removes <ifd> from its aggregated-Ethernet bundle, but only if doing so is
safe. Checks, in order; a failed check is logged and nothing is changed:

  1. MEMBER     <ifd> is configured as an 802.3ad member and is not already
                disabled or removed from its bundle.
  2. BACKUP     If backup-unit is set, that logical unit must be up with at
                least backup-min-nbrs OSPF neighbors. If it is not:
                  backup-down-min-remaining -1 (default): refuse.
                  backup-down-min-remaining N: carry on, but check 4 then
                  requires N (at least 1) active members to remain, whatever
                  min-remaining says.
  3. OWN BUNDLE Only with require-own-ospf yes: <ae>.<ae-unit> must be up
                with at least min-ospf-nbrs OSPF neighbors.
  4. REMAINING  If <ifd> is an active member, removing it must leave at least
                min-remaining active members (and never fewer than the
                bundle's minimum-links). min-remaining 0 turns this check off
                while the backup is healthy, so the last member can be
                removed and traffic fails over to the backup path. A member
                that is not active carries no traffic and is always removable.

"Active" means LACP collecting and distributing; in a bundle without LACP it
means the member link is up.

Action, in a private candidate, committed with a comment naming the link:

    set interfaces <ifd> disable
    deactivate interfaces <ifd> ether-options 802.3ad      (EVO)
    deactivate interfaces <ifd> gigether-options 802.3ad   (Junos)

Restoring the link is manual: delete the 'disable' and activate the 802.3ad
statement. A failed commit is logged; the alarm repeats on the next monitor
run, so the removal is retried.

Arguments (event-options policy <p> then event-script ber_remediate.py arguments):
    message                    (required) "{$$.message}"
    backup-unit                ""    backup logical unit, e.g. "ae10.0"; empty = no check 2
    backup-min-nbrs            "1"   OSPF neighbors required on backup-unit
    backup-down-min-remaining  "-1"  see check 2
    require-own-ospf           "no"  "yes" turns on check 3
    ae-unit                    "0"   unit of the member's own bundle used by check 3
    min-ospf-nbrs              "1"   OSPF neighbors required by check 3
    ospf-instance              ""    routing instance OSPF runs in; empty = master.
                                     Must be set when OSPF is in a routing instance,
                                     or no neighbors are found and checks 2/3 fail.
    min-remaining              "1"   see check 4

Syslog, facility daemon. Every line starts "BER-REMEDIATION: " and none
contains "HIGH BER", so the script cannot trigger itself:
    notice   progress, "is NOT a member of an AE bundle", "already disabled/removed"
    warning  "<ifd> has been disabled and removed from <ae>; ...", "... NOT removing ..."
    error    "commit FAILED ...", "unexpected error ...", "bad arguments ..."

Runs are serialized through LOCK_FILE, so when two members of one bundle
alarm together the second is judged after the first has been removed.
"""

import argparse
import fcntl
import re

from jcs import syslog
from jnpr.junos import Device
from jnpr.junos.utils.config import Config

__version__ = '5.0.0'

LOCK_FILE = '/var/tmp/ber_remediate.lock'
ALARM_RE = re.compile(r'HIGH BER \(via framing-errors\):\s*([A-Za-z0-9\-/.:]+)\s+has')
RPC_TIMEOUT = 120


def log(level, msg):
    syslog('daemon.' + level, 'BER-REMEDIATION: ' + msg)


def parse_args():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('-message', default='')
    ap.add_argument('-backup-unit', dest='backup_unit', default='')
    ap.add_argument('-backup-min-nbrs', dest='backup_min_nbrs', type=int, default=1)
    ap.add_argument('-backup-down-min-remaining', dest='backup_down_min_remaining',
                    type=int, default=-1)
    ap.add_argument('-require-own-ospf', dest='require_own_ospf', default='no')
    ap.add_argument('-ae-unit', dest='ae_unit', default='0')
    ap.add_argument('-min-ospf-nbrs', dest='min_ospf_nbrs', type=int, default=1)
    ap.add_argument('-ospf-instance', dest='ospf_instance', default='')
    ap.add_argument('-min-remaining', dest='min_remaining', type=int, default=1)
    args = ap.parse_args()          # SystemExit on bad arguments; handled in main()
    args.require_own_ospf = args.require_own_ospf.strip().lower() in ('yes', 'true', '1', 'on')
    return args


# ----------------------------------------------------------------------------
# Device queries. XPath uses local-name() so it works whatever namespace the
# platform puts on the reply.
# ----------------------------------------------------------------------------

def el(name):
    return "*[local-name()='{}']".format(name)


def first(node, expr):
    found = node.xpath(expr)
    return found[0] if found else None


def text(node, name):
    return (first(node, el(name) + '/text()') or '').strip()


def member_config(dev, ifname):
    """Return (bundle, disabled, branch) from the committed configuration.

    bundle    AE name, or None if ifname has no active 802.3ad statement
    disabled  True if 'disable' is configured (and not inactive)
    branch    'ether-options' / 'gigether-options' holding the 802.3ad
              statement, or None if there is none
    """
    filt = '<interfaces><interface><name>{}</name></interface></interfaces>'.format(ifname)
    cfg = dev.rpc.get_config(filter_xml=filt, options={'database': 'committed'})
    intf = first(cfg, "//{}[{}='{}']".format(el('interface'), el('name'), ifname))
    if intf is None:
        return None, False, None

    disable = first(intf, el('disable'))
    disabled = disable is not None and disable.get('inactive') != 'inactive'

    for branch in ('ether-options', 'gigether-options'):
        lag = first(intf, '{}/{}'.format(el(branch), el('ieee-802.3ad')))
        if lag is None:
            continue
        if lag.get('inactive') == 'inactive':
            return None, disabled, branch
        return text(lag, 'bundle') or None, disabled, branch
    return None, disabled, None


def minimum_links(dev, ae):
    """Configured minimum-links of ae, or 0 if it is not configured."""
    filt = ('<interfaces><interface><name>{}</name><aggregated-ether-options>'
            '<minimum-links/></aggregated-ether-options></interface></interfaces>').format(ae)
    cfg = dev.rpc.get_config(filter_xml=filt, options={'database': 'committed'})
    try:
        return int(first(cfg, '//' + el('minimum-links') + '/text()'))
    except (TypeError, ValueError):
        return 0


def active_members(dev, ae):
    """Return the members of ae that are carrying traffic.

    With LACP: actor state collecting and distributing. Without LACP (static
    bundle): member physical link up.
    """
    rsp = dev.rpc.get_lacp_interface_information(interface_name=ae)
    states = rsp.xpath('//' + el('lag-lacp-state'))
    if states:
        return [text(st, 'name') for st in states
                if text(st, 'lacp-role') == 'Actor'
                and text(st, 'lacp-collecting') == 'Yes'
                and text(st, 'lacp-distributing') == 'Yes']

    members = []
    rsp = dev.rpc.get_interface_information(terse=True)
    for phy in rsp.xpath('//' + el('physical-interface')):
        bundles = phy.xpath('.//{}/text()'.format(el('ae-bundle-name')))
        if (any(b.strip().split('.')[0] == ae for b in bundles)
                and text(phy, 'admin-status') == 'up' and text(phy, 'oper-status') == 'up'):
            members.append(text(phy, 'name'))
    return members


def unit_up(dev, unit):
    try:
        rsp = dev.rpc.get_interface_information(interface_name=unit, terse=True)
    except Exception:
        return False
    lif = first(rsp, '//' + el('logical-interface'))
    return (lif is not None
            and text(lif, 'admin-status') == 'up' and text(lif, 'oper-status') == 'up')


def ospf_neighbors(dev, unit, instance):
    """OSPF neighbor count on unit, or None if OSPF does not run on it."""
    kwargs = {'interface_name': unit}
    if instance:
        kwargs['instance'] = instance
    try:
        rsp = dev.rpc.get_ospf_interface_information(**kwargs)
        return int(first(rsp, "//{}[normalize-space({})='{}']/{}/text()".format(
            el('ospf-interface'), el('interface-name'), unit, el('neighbor-count'))))
    except Exception:
        return None


def unit_status(dev, unit, need, instance):
    """Return (healthy, description): unit up with at least `need` OSPF neighbors."""
    up = unit_up(dev, unit)
    nbrs = ospf_neighbors(dev, unit, instance)
    return (up and nbrs is not None and nbrs >= need,
            '{} up={} ospf_nbrs={}'.format(unit, up, nbrs))


# ----------------------------------------------------------------------------
# Decision and action
# ----------------------------------------------------------------------------

def remediate(dev, ifname, args):
    # 1. Member
    bundle, disabled, branch = member_config(dev, ifname)
    if disabled or (branch and bundle is None):
        log('notice', '{} already disabled/removed from its bundle; nothing to do.'.format(ifname))
        return
    if bundle is None:
        log('notice', '{} is NOT a member of an AE bundle; no action.'.format(ifname))
        return
    log('notice', 'sustained high BER on {} (member of {}); evaluating removal '
                  '[ber_remediate {}].'.format(ifname, bundle, __version__))

    # 2. Backup path
    backup_down = ''
    if args.backup_unit:
        healthy, status = unit_status(dev, args.backup_unit, args.backup_min_nbrs,
                                      args.ospf_instance)
        if healthy:
            log('notice', 'backup {}: OK.'.format(status))
        elif args.backup_down_min_remaining < 0:
            log('warning', 'backup {} (need >= {}); NOT removing {}.'.format(
                status, args.backup_min_nbrs, ifname))
            return
        else:
            backup_down = 'backup {} is DOWN'.format(args.backup_unit)
            log('notice', 'backup {} (need >= {}): DOWN; {} must keep >= {} active member(s).'
                .format(status, args.backup_min_nbrs, bundle,
                        max(args.backup_down_min_remaining, 1)))

    # 3. Own bundle
    if args.require_own_ospf:
        healthy, status = unit_status(dev, '{}.{}'.format(bundle, args.ae_unit),
                                      args.min_ospf_nbrs, args.ospf_instance)
        if not healthy:
            log('warning', '{} (need >= {}); NOT removing {}.'.format(
                status, args.min_ospf_nbrs, ifname))
            return

    # 4. Remaining members
    active = active_members(dev, bundle)
    remaining = [m for m in active if m != ifname]
    if backup_down:
        need = max(args.backup_down_min_remaining, minimum_links(dev, bundle), 1)
    elif args.min_remaining > 0:
        need = max(args.min_remaining, minimum_links(dev, bundle))
    else:
        need = 0
    if ifname not in active:
        log('notice', '{} is not an active member of {} (active: {}); '
                      'remaining-member check not needed.'.format(ifname, bundle, active))
    elif len(remaining) < need:
        log('warning', '{}removing {} would leave {} active member(s) in {} {} (need >= {}); '
                       'NOT removing.'.format(backup_down + ' and ' if backup_down else '',
                                              ifname, len(remaining), bundle, remaining, need))
        return

    # Act
    change = ('set interfaces {ifd} disable\n'
              'deactivate interfaces {ifd} {branch} 802.3ad').format(ifd=ifname, branch=branch)
    comment = '{} disabled and removed from {} (sustained high BER)'.format(ifname, bundle)
    try:
        with Config(dev, mode='private') as cu:
            cu.load(change, format='set', merge=True)
            cu.commit(comment=comment, timeout=RPC_TIMEOUT)
    except Exception as e:
        log('error', 'commit FAILED for {}: {}'.format(ifname, e))
        return
    log('warning', '{} has been disabled and removed from {}; {} active member(s) remain {}{}.'
        .format(ifname, bundle, len(remaining), remaining,
                '; ' + backup_down if backup_down else ''))


def main():
    try:
        args = parse_args()
    except SystemExit:
        log('error', 'bad arguments; not running.')
        return

    alarm = ALARM_RE.search(args.message)
    if not alarm:
        return                      # not a HIGH BER alarm; nothing to do
    ifname = alarm.group(1)

    with open(LOCK_FILE, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with Device() as dev:
                dev.timeout = RPC_TIMEOUT
                remediate(dev, ifname, args)
        except Exception as e:
            log('error', 'unexpected error handling {}: {}'.format(ifname, e))


if __name__ == '__main__':
    main()
