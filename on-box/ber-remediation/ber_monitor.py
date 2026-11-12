#!/usr/bin/env python3
"""ber_monitor.py - Junos / Junos EVO event script: sustained framing-error BER alarm.

Run every <interval> seconds by an 'event-options generate-event' policy. On
each run, for every monitored interface, it reads the framing-error and
input-byte counters and compares the error rate since the previous run with
the rate a given bit-error ratio would allow:

    allowed errors/s = input bits/s * threshold
    breach           = input bits/s > 0 and framing errors/s >= allowed errors/s

Breaches are counted per interface. A breach that has not yet lasted <sustain>
consecutive runs is logged as

    BER-SAMPLE breach n/N on <ifd>: ...

From the <sustain>th consecutive breach on, every breaching run logs the alarm
that ber_remediate.py acts on:

    HIGH BER (via framing-errors): <ifd> has ... [sustained n/N samples]

A run without a breach resets the count. The first run for an interface, a run
after a gap of more than 3 x <interval>, and a run that finds a counter has
gone backwards (statistics cleared) only record a new baseline.

Arguments (event-options policy <p> then event-script ber_monitor.py arguments):
    interfaces  (required)  comma-separated physical interfaces,
                            e.g. "et-0/0/5,et-0/0/6"
    threshold   "1e-7"      bit-error ratio (framing errors per input bit).
                            0 makes every run with traffic a breach; use it
                            only to exercise the alarm path in a lab.
    sustain     "3"         consecutive breaching runs before HIGH BER
    interval    "60"        seconds between runs; must match the
                            generate-event time-interval

Syslog, facility daemon:
    warning  HIGH BER (via framing-errors): <ifd> has ...
    notice   BER-SAMPLE breach n/N on <ifd>: ...
    notice   BER-MONITOR: previous run still active; skipping
    error    BER-MONITOR: <what went wrong>

Files: STATE_FILE holds the previous counters and breach counts; LOCK_FILE
stops two runs from overlapping.
"""

import argparse
import fcntl
import json
import os
import time

from jcs import syslog
from jnpr.junos import Device

__version__ = '5.0.0'

STATE_FILE = '/var/tmp/ber_monitor.json'
LOCK_FILE = '/var/tmp/ber_monitor.lock'
MAX_GAP_INTERVALS = 3       # a longer gap between samples starts a new baseline

# Counter name -> XPath below <physical-interface> (namespace-agnostic).
COUNTERS = {
    'framing_errors':
        ".//*[local-name()='framing-errors']/text()",
    'input_bytes':
        ".//*[local-name()='traffic-statistics']/*[local-name()='input-bytes']/text()",
    'bit_error_seconds':
        ".//*[local-name()='ethernet-pcs-statistics']/*[local-name()='bit-error-seconds']/text()",
    'errored_blocks_seconds':
        ".//*[local-name()='ethernet-pcs-statistics']/*[local-name()='errored-blocks-seconds']/text()",
}


class ArgumentError(Exception):
    pass


def log_error(msg):
    syslog('daemon.error', 'BER-MONITOR: ' + msg)


def parse_args():
    """Return (interfaces, threshold, sustain, interval) or raise ArgumentError."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('-interfaces', default='')
    ap.add_argument('-threshold', default='1e-7')
    ap.add_argument('-sustain', default='3')
    ap.add_argument('-interval', default='60')
    try:
        args = ap.parse_args()
    except SystemExit:
        raise ArgumentError('unrecognized arguments')

    interfaces = []
    for name in args.interfaces.split(','):
        name = name.strip()
        if name and name not in interfaces:
            interfaces.append(name)
    if not interfaces:
        raise ArgumentError('no interfaces specified')

    try:
        threshold = float(args.threshold)
        sustain = int(args.sustain)
        interval = int(args.interval)
    except ValueError:
        raise ArgumentError('threshold, sustain and interval must be numbers')
    if not (0 <= threshold < 1) or sustain < 1 or interval < 1:
        raise ArgumentError('need 0 <= threshold < 1, sustain >= 1, interval >= 1')
    return interfaces, threshold, sustain, interval


def load_state():
    """Return {ifname: {'counters': {...}, 'ts': int, 'breaches': int}}."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        interfaces = state['interfaces']
        return interfaces if isinstance(interfaces, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_state(interfaces):
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'version': __version__, 'interfaces': interfaces}, f)
    os.replace(tmp, STATE_FILE)


def read_counters(dev, ifname):
    """Return {counter: value} for ifname, or None if the interface is unknown."""
    rsp = dev.rpc.get_interface_information(interface_name=ifname, extensive=True)
    found = rsp.xpath("//*[local-name()='physical-interface']")
    if not found:
        return None
    counters = {}
    for name, expr in COUNTERS.items():
        text = found[0].xpath(expr)
        try:
            counters[name] = int(text[0])
        except (IndexError, ValueError):
            counters[name] = 0      # counter not reported on this platform
    return counters


def sample(ifname, previous, counters, now, threshold, sustain, interval):
    """Compare counters with the previous sample, log, and return the new state."""
    baseline = {'counters': counters, 'ts': now, 'breaches': 0}
    try:
        elapsed = now - previous['ts']
        delta = {k: counters[k] - previous['counters'][k] for k in COUNTERS}
        breaches = int(previous['breaches'])
    except (KeyError, TypeError, ValueError):
        return baseline             # no usable previous sample
    if not 0 < elapsed <= MAX_GAP_INTERVALS * interval or min(delta.values()) < 0:
        return baseline             # gap too long, clock stepped, or stats cleared

    bps = delta['input_bytes'] * 8.0 / elapsed
    error_rate = float(delta['framing_errors']) / elapsed
    allowed = bps * threshold
    if not (bps > 0 and error_rate >= allowed):
        return baseline

    breaches += 1
    detail = (
        'framing-errors={rate:.2f}/s, allowed={allowed:.2f}/s over last {elapsed}s '
        '(BER threshold {threshold:.1e}); Framing Error Delta={framing_errors}, '
        'Input Bytes Delta={input_bytes} (~{byte_rate:.0f} B/s), '
        'Bit-Errors-Sec Delta={bit_error_seconds}, '
        'Errored-Block-Sec Delta={errored_blocks_seconds}, bps={bps:.2e}'
    ).format(rate=error_rate, allowed=allowed, elapsed=elapsed, threshold=threshold,
             byte_rate=delta['input_bytes'] / float(elapsed), bps=bps, **delta)
    if breaches >= sustain:
        syslog('daemon.warning',
               'HIGH BER (via framing-errors): {} has {} [sustained {}/{} samples]'.format(
                   ifname, detail, breaches, sustain))
    else:
        syslog('daemon.notice',
               'BER-SAMPLE breach {}/{} on {}: {}'.format(breaches, sustain, ifname, detail))
    return {'counters': counters, 'ts': now, 'breaches': breaches}


def run(interfaces, threshold, sustain, interval):
    previous = load_state()
    state = {}
    now = int(time.time())
    with Device() as dev:
        for ifname in interfaces:
            try:
                counters = read_counters(dev, ifname)
            except Exception as e:
                log_error('error reading {}: {}'.format(ifname, e))
                continue            # no state kept: next good run is a baseline
            if counters is None:
                log_error('interface {} not found'.format(ifname))
                continue
            state[ifname] = sample(ifname, previous.get(ifname), counters, now,
                                   threshold, sustain, interval)
    save_state(state)               # interfaces no longer monitored are dropped


def main():
    try:
        settings = parse_args()
    except ArgumentError as e:
        log_error('{}; not running'.format(e))
        return

    with open(LOCK_FILE, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            syslog('daemon.notice', 'BER-MONITOR: previous run still active; skipping')
            return
        try:
            run(*settings)
        except Exception as e:
            log_error('run failed: {}'.format(e))


if __name__ == '__main__':
    main()
