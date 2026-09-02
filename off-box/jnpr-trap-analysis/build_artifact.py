#!/usr/bin/env python3
"""Renders juniper_notifications_full.json (produced by build_full_catalog.py,
which must be run first) into a self-contained, standalone juniper_trap_catalog.html
you can open directly in a browser - no server needed."""
import json
from pathlib import Path

SNMP_ROOT = Path(__file__).resolve().parent
payload = json.loads((SNMP_ROOT / "juniper_notifications_full.json").read_text())
release_labels = payload["release_labels"]
junos_versions = payload["junos_versions"]
evo_versions = payload["evo_versions"]
include_standard = payload["include_standard"]
registry = payload["registry"]

CATEGORY_LABELS = {
    "other": "Other",
    "chassis-hardware": "Chassis & hardware",
    "routing": "Routing & switching protocols",
    "mobile-core": "Mobile gateway & core",
    "security": "Security & policy",
    "timing": "Timing & synchronization",
    "interfaces-optics": "Interfaces & optics",
    "ha": "High availability",
    "monitoring-probes": "Monitoring & probes",
    "platform-system": "Platform & system",
}

total_union = len(registry)
both_count = sum(1 for r in registry if r["os_scope"] == "Both")
junos_only_count = sum(1 for r in registry if r["os_scope"] == "Junos only")
evo_only_count = sum(1 for r in registry if r["os_scope"] == "Junos-EVO only")
n_releases = len(release_labels)
scope_note = "Juniper-enterprise + standards-track" if include_standard else "Juniper-enterprise files only"

json_blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
cat_labels_blob = json.dumps(CATEGORY_LABELS, separators=(",", ":"))

html = f"""<title>Juniper trap catalog</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
  :root {{
    --bg: #EEF2F4;
    --surface: #FFFFFF;
    --surface-2: #F5F8F9;
    --ink: #121A21;
    --ink-secondary: #4E5D68;
    --ink-muted: #869097;
    --border: #D7DEE2;
    --border-strong: #B7C2C8;
    --accent: #0E6E82;
    --accent-ink: #06414C;
    --accent-tint: #DCEEF1;
    --tag-std-bg: #F5E8D2;
    --tag-std-ink: #7A4E10;
    --decoded-tint: #ECE5F7;
    --decoded-ink: #5B3C8C;
    --added-tint: #E1F0DE;
    --added-ink: #2C6B1F;
    --removed-tint: #FBE1E1;
    --removed-ink: #9A2C2C;
    --changed-tint: #FDECC8;
    --changed-ink: #8A5A0B;
    --unchanged-tint: #EAEAE6;
    --unchanged-ink: #5B5B56;
    --shadow-color: 20, 26, 33;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #0D1316;
      --surface: #161E22;
      --surface-2: #1B242A;
      --ink: #E8EDEF;
      --ink-secondary: #AAB6BC;
      --ink-muted: #6D7A80;
      --border: #26323A;
      --border-strong: #3A4A51;
      --accent: #4FB8CC;
      --accent-ink: #BEEAF1;
      --accent-tint: #16333A;
      --tag-std-bg: #3A2E12;
      --tag-std-ink: #E8B563;
      --decoded-tint: #2B2038;
      --decoded-ink: #CBA8EA;
      --added-tint: #1C3318;
      --added-ink: #9AD98A;
      --removed-tint: #3A1F1F;
      --removed-ink: #E8A0A0;
      --changed-tint: #3A2E12;
      --changed-ink: #E8B563;
      --unchanged-tint: #22282C;
      --unchanged-ink: #9AA3A8;
      --shadow-color: 0, 0, 0;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #0D1316;
    --surface: #161E22;
    --surface-2: #1B242A;
    --ink: #E8EDEF;
    --ink-secondary: #AAB6BC;
    --ink-muted: #6D7A80;
    --border: #26323A;
    --border-strong: #3A4A51;
    --accent: #4FB8CC;
    --accent-ink: #BEEAF1;
    --accent-tint: #16333A;
    --tag-std-bg: #3A2E12;
    --tag-std-ink: #E8B563;
    --decoded-tint: #2B2038;
    --decoded-ink: #CBA8EA;
    --added-tint: #1C3318;
    --added-ink: #9AD98A;
    --removed-tint: #3A1F1F;
    --removed-ink: #E8A0A0;
    --changed-tint: #3A2E12;
    --changed-ink: #E8B563;
    --unchanged-tint: #22282C;
    --unchanged-ink: #9AA3A8;
    --shadow-color: 0, 0, 0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--ink);
    font-family: 'Public Sans', system-ui, -apple-system, sans-serif;
    padding: 1.5rem 1.25rem 3rem;
    max-width: 960px;
    margin: 0 auto;
  }}
  ::selection {{ background: var(--accent-tint); color: var(--accent-ink); }}
  a {{ color: var(--accent); }}

  .mast {{ margin-bottom: 1.75rem; }}
  .eyebrow {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent-ink);
    background: var(--accent-tint);
    display: inline-block;
    padding: 3px 9px;
    border-radius: 4px;
    margin: 0 0 0.9rem;
  }}
  h1 {{
    font-size: 32px;
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: -0.01em;
    margin: 0 0 0.6rem;
    text-wrap: balance;
  }}
  .dek {{
    font-size: 15px;
    line-height: 1.6;
    color: var(--ink-secondary);
    max-width: 66ch;
    margin: 0 0 1.5rem;
  }}
  .dek code {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    background: var(--surface-2);
    border: 0.5px solid var(--border);
    padding: 1px 5px;
    border-radius: 4px;
  }}

  .stats {{
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
  }}
  .stat {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem 0.85rem;
  }}
  .stat-value {{
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }}
  .stat-label {{
    display: block;
    font-size: 12px;
    color: var(--ink-muted);
    margin-top: 4px;
    line-height: 1.35;
  }}
  .stat-accent {{ border-color: var(--accent); }}
  .stat-accent .stat-value {{ color: var(--accent-ink); }}

  .mode-toggle {{
    display: inline-flex;
    border: 0.5px solid var(--border-strong);
    border-radius: 8px;
    overflow: hidden;
    margin: 1.1rem 0 0.75rem;
  }}
  .mode-btn {{
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    background: var(--surface);
    color: var(--ink-secondary);
    border: none;
    padding: 7px 16px;
    cursor: pointer;
  }}
  .mode-btn + .mode-btn {{ border-left: 0.5px solid var(--border-strong); }}
  .mode-btn[aria-pressed="true"] {{ background: var(--accent); color: #fff; }}

  .controls {{
    position: sticky;
    top: 0;
    z-index: 5;
    background: var(--bg);
    padding: 0.65rem 0 0.65rem;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    border-bottom: 0.5px solid var(--border);
    margin-bottom: 0.85rem;
  }}
  .controls input[type="search"] {{ flex: 1 1 220px; }}
  .controls select {{ flex: 0 0 auto; }}
  .compare-arrow {{ color: var(--ink-muted); font-size: 13px; }}
  .diff-toggle {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--ink-secondary);
    white-space: nowrap;
  }}
  .diff-toggle input {{ width: 15px; height: 15px; accent-color: var(--accent); }}

  input, select {{
    background: var(--surface);
    color: var(--ink);
    border: 0.5px solid var(--border-strong);
    border-radius: 8px;
    height: 36px;
    padding: 0 10px;
    font-family: 'Public Sans', sans-serif;
    font-size: 14px;
  }}
  input[type="search"] {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; }}
  input:focus-visible, select:focus-visible, button:focus-visible {{
    outline: none;
    box-shadow: 0 0 0 2px var(--accent);
  }}

  .count {{
    font-size: 12.5px;
    color: var(--ink-muted);
    margin: 0 0 0.75rem;
    font-variant-numeric: tabular-nums;
  }}

  .list {{ display: flex; flex-direction: column; gap: 6px; }}

  .entry {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  .entry-head {{
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 13px;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    color: var(--ink);
    font: inherit;
  }}
  .entry-head:hover {{ background: var(--surface-2); }}
  .entry-id {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
  .entry-name {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13.5px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .entry-sub {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .entry-oid {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    color: var(--ink-muted);
  }}
  .presence {{ display: flex; gap: 3px; }}
  .presence-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--border-strong);
  }}
  .presence-dot[data-present="true"] {{ background: var(--accent); }}
  .entry-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }}
  .entry-module {{
    font-size: 11.5px;
    color: var(--ink-secondary);
    font-family: 'JetBrains Mono', monospace;
    max-width: 22ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .badge {{
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    padding: 2px 7px;
    border-radius: 999px;
    flex-shrink: 0;
  }}
  .badge-enterprise {{ background: var(--accent-tint); color: var(--accent-ink); }}
  .badge-standard {{ background: var(--tag-std-bg); color: var(--tag-std-ink); }}
  .badge-decoded {{ background: var(--decoded-tint); color: var(--decoded-ink); }}
  .badge-added {{ background: var(--added-tint); color: var(--added-ink); }}
  .badge-removed {{ background: var(--removed-tint); color: var(--removed-ink); }}
  .badge-changed {{ background: var(--changed-tint); color: var(--changed-ink); }}
  .badge-unchanged {{ background: var(--unchanged-tint); color: var(--unchanged-ink); }}
  .chevron {{
    width: 14px; height: 14px;
    flex-shrink: 0;
    transition: transform 0.15s ease;
    color: var(--ink-muted);
  }}
  .entry[data-open="true"] .chevron {{ transform: rotate(180deg); }}

  .entry-body {{
    display: none;
    padding: 0 13px 13px;
    border-top: 0.5px solid var(--border);
  }}
  .entry[data-open="true"] .entry-body {{ display: block; }}

  .snapshot {{ margin-top: 11px; }}
  .snapshot + .snapshot {{ margin-top: 14px; padding-top: 14px; border-top: 0.5px dashed var(--border); }}
  .snapshot-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: var(--ink-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 7px;
  }}
  .field-flag {{
    font-size: 10px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    color: var(--changed-ink);
    background: var(--changed-tint);
    padding: 1px 6px;
    border-radius: 999px;
  }}
  .entry-desc {{
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--ink-secondary);
    margin: 0 0 10px;
    max-width: 68ch;
  }}
  .oid-line {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--ink-secondary);
    margin-bottom: 10px;
  }}
  .objects-label {{
    color: var(--ink-muted);
    text-transform: uppercase;
    font-size: 10.5px;
    letter-spacing: 0.05em;
    display: block;
    margin-bottom: 6px;
  }}
  .varbinds {{
    display: flex;
    flex-direction: column;
    gap: 9px;
    margin-bottom: 4px;
  }}
  .varbind-head {{
    display: flex;
    align-items: baseline;
    gap: 7px;
    flex-wrap: wrap;
  }}
  .varbind-name {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
  }}
  .varbind-type {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-muted);
  }}
  .varbind-enum {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px 6px;
    margin-top: 5px;
  }}
  .enum-pill {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    background: var(--decoded-tint);
    color: var(--decoded-ink);
    padding: 1px 7px;
    border-radius: 4px;
    white-space: nowrap;
  }}
  .enum-pill[data-delta="added"] {{ background: var(--added-tint); color: var(--added-ink); box-shadow: inset 0 0 0 1px var(--added-ink); }}
  .enum-pill[data-delta="removed"] {{ background: var(--removed-tint); color: var(--removed-ink); text-decoration: line-through; opacity: 0.8; }}
  .entry-file {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-muted);
    margin-top: 8px;
  }}
  .diff-note {{
    font-size: 12px;
    color: var(--ink-muted);
    margin: 10px 0 0;
    font-style: italic;
  }}

  .empty {{
    padding: 2.5rem 1rem;
    text-align: center;
    color: var(--ink-muted);
    font-size: 14px;
  }}

  @media (max-width: 700px) {{
    .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    h1 {{ font-size: 26px; }}
    .controls {{ position: static; }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    .chevron {{ transition: none; }}
  }}
</style>

<header class="mast">
  <p class="eyebrow">Junos &amp; Junos-EVO SNMP reference &middot; {n_releases} releases loaded &middot; {scope_note}</p>
  <h1>Juniper trap catalog</h1>
  <p class="dek">Every SNMP notification across the loaded Junos and Junos-EVO MIB releases, parsed from the <code>NOTIFICATION-TYPE</code> declarations, with each varbind cross-referenced against its <code>OBJECT-TYPE</code> for decoded enum values. Browse a single release, or compare any two &mdash; including across operating systems &mdash; to see exactly what was added, removed, or changed.</p>
  <div class="stats" role="group" aria-label="Catalog totals">
    <div class="stat stat-accent"><span class="stat-value">{total_union}</span><span class="stat-label">Unique traps (all releases)</span></div>
    <div class="stat"><span class="stat-value">{both_count}</span><span class="stat-label">On both Junos &amp; Junos-EVO</span></div>
    <div class="stat"><span class="stat-value">{junos_only_count}</span><span class="stat-label">Junos only</span></div>
    <div class="stat"><span class="stat-value">{evo_only_count}</span><span class="stat-label">Junos-EVO only</span></div>
    <div class="stat"><span class="stat-value">{n_releases}</span><span class="stat-label">Releases loaded</span></div>
  </div>
  <div class="mode-toggle" role="group" aria-label="View mode">
    <button type="button" class="mode-btn" id="mode-browse" aria-pressed="true">Browse a release</button>
    <button type="button" class="mode-btn" id="mode-compare" aria-pressed="false">Compare releases</button>
  </div>
</header>

<div class="controls" id="controls-browse">
  <input type="search" id="q" placeholder="Search name, OID, module, description&hellip;" aria-label="Search traps" autocomplete="off">
  <select id="browse_version" aria-label="Choose release"></select>
  <select id="scope" aria-label="Filter by scope">
    <option value="enterprise" selected>Juniper-enterprise only</option>
    <option value="all">All notifications</option>
    <option value="standard">Standards-track only</option>
  </select>
  <select id="os_scope_filter" aria-label="Filter by OS availability">
    <option value="all">Any OS</option>
    <option value="Both">On both OSes</option>
    <option value="Junos only">Junos only</option>
    <option value="Junos-EVO only">Junos-EVO only</option>
  </select>
  <select id="category" aria-label="Filter by category">
    <option value="all">All categories</option>
  </select>
  <select id="decoded_filter" aria-label="Filter by decoded values">
    <option value="all">All varbind types</option>
    <option value="decoded">Has decoded values</option>
  </select>
  <select id="sort" aria-label="Sort order">
    <option value="module">Sort: module</option>
    <option value="name">Sort: name A&ndash;Z</option>
  </select>
</div>

<div class="controls" id="controls-compare" hidden>
  <input type="search" id="q2" placeholder="Search name, OID, module, description&hellip;" aria-label="Search traps" autocomplete="off">
  <select id="from_version" aria-label="Compare from release"></select>
  <span class="compare-arrow">&rarr;</span>
  <select id="to_version" aria-label="Compare to release"></select>
  <select id="status_filter" aria-label="Filter by change status">
    <option value="changes">Added, removed &amp; changed</option>
    <option value="all">All (incl. unchanged)</option>
    <option value="added">Added only</option>
    <option value="removed">Removed only</option>
    <option value="changed">Changed only</option>
  </select>
  <select id="category2" aria-label="Filter by category">
    <option value="all">All categories</option>
  </select>
</div>

<p id="count" class="count" aria-live="polite"></p>
<div id="list" class="list"></div>

<script type="application/json" id="trap-data">{json_blob}</script>
<script type="application/json" id="category-labels">{cat_labels_blob}</script>
<script>
(function() {{
  var payload = JSON.parse(document.getElementById('trap-data').textContent);
  var CATEGORY_LABELS = JSON.parse(document.getElementById('category-labels').textContent);
  var JUNOS_VERSIONS = payload.junos_versions;
  var EVO_VERSIONS = payload.evo_versions;
  var VERSIONS = payload.release_labels;
  var registry = payload.registry;

  var qEl = document.getElementById('q');
  var q2El = document.getElementById('q2');
  var browseVersionEl = document.getElementById('browse_version');
  var scopeEl = document.getElementById('scope');
  var osScopeFilterEl = document.getElementById('os_scope_filter');
  var categoryEl = document.getElementById('category');
  var decodedEl = document.getElementById('decoded_filter');
  var sortEl = document.getElementById('sort');
  var fromVersionEl = document.getElementById('from_version');
  var toVersionEl = document.getElementById('to_version');
  var statusFilterEl = document.getElementById('status_filter');
  var category2El = document.getElementById('category2');
  var countEl = document.getElementById('count');
  var listEl = document.getElementById('list');
  var modeBrowseBtn = document.getElementById('mode-browse');
  var modeCompareBtn = document.getElementById('mode-compare');
  var controlsBrowse = document.getElementById('controls-browse');
  var controlsCompare = document.getElementById('controls-compare');

  var mode = 'browse';
  var openState = Object.create(null);
  var debounceTimer = null;

  var defaultBrowse = 'Junos ' + JUNOS_VERSIONS[JUNOS_VERSIONS.length - 1];
  var defaultFrom = 'Junos ' + JUNOS_VERSIONS[JUNOS_VERSIONS.length - 1];
  var defaultTo = 'Junos-EVO ' + EVO_VERSIONS[EVO_VERSIONS.length - 1];

  // ---- populate version selects, grouped by OS ----
  function fillVersionSelect(sel, defaultValue) {{
    [['Junos', JUNOS_VERSIONS], ['Junos-EVO', EVO_VERSIONS]].forEach(function(pair) {{
      var osName = pair[0], versions = pair[1];
      if (!versions.length) return;
      var group = document.createElement('optgroup');
      group.label = osName;
      versions.forEach(function(v) {{
        var label = osName + ' ' + v;
        var opt = document.createElement('option');
        opt.value = label;
        opt.textContent = v;
        if (label === defaultValue) opt.selected = true;
        group.appendChild(opt);
      }});
      sel.appendChild(group);
    }});
  }}
  fillVersionSelect(browseVersionEl, defaultBrowse);
  fillVersionSelect(fromVersionEl, defaultFrom);
  fillVersionSelect(toVersionEl, defaultTo);

  // ---- populate category selects ----
  var catCounts = {{}};
  registry.forEach(function(r) {{ catCounts[r.category] = (catCounts[r.category] || 0) + 1; }});
  [categoryEl, category2El].forEach(function(sel) {{
    Object.keys(catCounts).sort(function(a, b) {{ return catCounts[b] - catCounts[a]; }}).forEach(function(cat) {{
      var opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = (CATEGORY_LABELS[cat] || cat) + ' (' + catCounts[cat] + ')';
      sel.appendChild(opt);
    }});
  }});

  function varbindsHaveEnum(vb) {{
    return (vb || []).some(function(v) {{ return v.enum && Object.keys(v.enum).length; }});
  }}
  function varbindsText(vb) {{
    return (vb || []).map(function(v) {{
      if (!v.enum) return v.name;
      var keys = Object.keys(v.enum).sort(function(a,b){{return Number(a)-Number(b);}});
      return v.name + ':' + keys.map(function(k){{ return k + '=' + v.enum[k]; }}).join(',');
    }}).join('|');
  }}

  function matchesQuery(name, module, oid, description, varbinds, q) {{
    if (!q) return true;
    if (name.toLowerCase().indexOf(q) !== -1) return true;
    if (oid.toLowerCase().indexOf(q) !== -1) return true;
    if (module.toLowerCase().indexOf(q) !== -1) return true;
    if (description.toLowerCase().indexOf(q) !== -1) return true;
    for (var i = 0; i < (varbinds || []).length; i++) {{
      var v = varbinds[i];
      if (v.name.toLowerCase().indexOf(q) !== -1) return true;
      if (v.enum) {{
        for (var key in v.enum) {{
          if (v.enum[key].toLowerCase().indexOf(q) !== -1) return true;
        }}
      }}
    }}
    return false;
  }}

  function buildChevron() {{
    var chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('viewBox', '0 0 16 16');
    chevron.setAttribute('class', 'chevron');
    chevron.setAttribute('aria-hidden', 'true');
    chevron.innerHTML = '<path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>';
    return chevron;
  }}

  function buildPresenceDots(r) {{
    var wrap = document.createElement('div');
    wrap.className = 'presence';
    var presentLabels = VERSIONS.filter(function(v) {{ return r.versions[v].present; }});
    wrap.title = (presentLabels.length ? 'Present in: ' + presentLabels.join(', ') : 'Not present in any loaded release');
    [['Junos', JUNOS_VERSIONS], ['Junos-EVO', EVO_VERSIONS]].forEach(function(pair, gi) {{
      var osName = pair[0], versions = pair[1];
      if (gi > 0 && versions.length) {{
        var gap = document.createElement('span');
        gap.style.width = '5px';
        wrap.appendChild(gap);
      }}
      versions.forEach(function(v) {{
        var label = osName + ' ' + v;
        var dot = document.createElement('span');
        dot.className = 'presence-dot';
        dot.dataset.present = r.versions[label].present ? 'true' : 'false';
        wrap.appendChild(dot);
      }});
    }});
    return wrap;
  }}

  function buildVarbindBlock(varbinds, diffAgainst) {{
    var wrap = document.createElement('div');
    if (!varbinds || !varbinds.length) return wrap;
    var label = document.createElement('span');
    label.className = 'objects-label';
    label.textContent = 'Varbinds';
    wrap.appendChild(label);

    var vbWrap = document.createElement('div');
    vbWrap.className = 'varbinds';
    var diffMap = {{}};
    if (diffAgainst) {{
      diffAgainst.forEach(function(v) {{ diffMap[v.name] = v; }});
    }}
    varbinds.forEach(function(v) {{
      var row = document.createElement('div');
      row.className = 'varbind';
      var vHead = document.createElement('div');
      vHead.className = 'varbind-head';
      var vName = document.createElement('span');
      vName.className = 'varbind-name';
      vName.textContent = v.name;
      vHead.appendChild(vName);
      if (v.base) {{
        var vType = document.createElement('span');
        vType.className = 'varbind-type';
        vType.textContent = v.base;
        vHead.appendChild(vType);
      }}
      row.appendChild(vHead);

      if (v.enum) {{
        var keys = Object.keys(v.enum).sort(function(a, b) {{ return Number(a) - Number(b); }});
        var other = diffMap[v.name];
        var pillWrap = document.createElement('div');
        pillWrap.className = 'varbind-enum';
        keys.forEach(function(k) {{
          var pill = document.createElement('span');
          pill.className = 'enum-pill';
          pill.textContent = k + ' = ' + v.enum[k];
          if (other && other.enum && !(k in other.enum)) pill.dataset.delta = 'added';
          pillWrap.appendChild(pill);
        }});
        if (other && other.enum) {{
          Object.keys(other.enum).forEach(function(k) {{
            if (!(k in v.enum)) {{
              var rpill = document.createElement('span');
              rpill.className = 'enum-pill';
              rpill.dataset.delta = 'removed';
              rpill.textContent = k + ' = ' + other.enum[k];
              pillWrap.appendChild(rpill);
            }}
          }});
        }}
        row.appendChild(pillWrap);
      }}
      vbWrap.appendChild(row);
    }});
    wrap.appendChild(vbWrap);
    return wrap;
  }}

  function buildSnapshot(label, snap, flags, diffAgainst) {{
    var box = document.createElement('div');
    box.className = 'snapshot';

    var head = document.createElement('div');
    head.className = 'snapshot-label';
    var labelText = document.createElement('span');
    labelText.textContent = label;
    head.appendChild(labelText);
    (flags || []).forEach(function(f) {{
      var flag = document.createElement('span');
      flag.className = 'field-flag';
      flag.textContent = f;
      head.appendChild(flag);
    }});
    box.appendChild(head);

    var oidLine = document.createElement('div');
    oidLine.className = 'oid-line';
    oidLine.textContent = snap.oid + (snap.status ? '  \\u00b7  status: ' + snap.status : '');
    box.appendChild(oidLine);

    var desc = document.createElement('p');
    desc.className = 'entry-desc';
    desc.textContent = snap.description || '(no description in MIB)';
    box.appendChild(desc);

    box.appendChild(buildVarbindBlock(snap.objects_detail, diffAgainst));

    var fileEl = document.createElement('div');
    fileEl.className = 'entry-file';
    fileEl.textContent = 'Defined in ' + snap.file;
    box.appendChild(fileEl);

    return box;
  }}

  function snapshotsDiffer(a, b) {{
    if (a.oid !== b.oid) return true;
    if (a.description !== b.description) return true;
    if (varbindsText(a.objects_detail) !== varbindsText(b.objects_detail)) return true;
    return false;
  }}

  // ============ BROWSE MODE ============
  function renderBrowse() {{
    var q = qEl.value.trim().toLowerCase();
    var version = browseVersionEl.value;
    var scope = scopeEl.value;
    var osScope = osScopeFilterEl.value;
    var category = categoryEl.value;
    var decodedOnly = decodedEl.value === 'decoded';
    var sort = sortEl.value;

    var rows = [];
    registry.forEach(function(r) {{
      var snap = r.versions[version];
      if (!snap.present) return;
      if (scope === 'enterprise' && !snap.juniper_enterprise) return;
      if (scope === 'standard' && snap.juniper_enterprise) return;
      if (osScope !== 'all' && r.os_scope !== osScope) return;
      if (category !== 'all' && r.category !== category) return;
      var decoded = varbindsHaveEnum(snap.objects_detail);
      if (decodedOnly && !decoded) return;
      if (!matchesQuery(r.name, snap.module, snap.oid, snap.description, snap.objects_detail, q)) return;
      rows.push({{ r: r, snap: snap, decoded: decoded }});
    }});

    rows.sort(function(a, b) {{
      if (sort === 'name') return a.r.name.localeCompare(b.r.name);
      return a.snap.module.localeCompare(b.snap.module) || a.r.name.localeCompare(b.r.name);
    }});

    countEl.textContent = rows.length + (rows.length === 1 ? ' notification' : ' notifications') + ' in ' + version +
      (q || category !== 'all' || scope !== 'enterprise' || osScope !== 'all' || decodedOnly ? ' matching your filters' : '');

    listEl.innerHTML = '';
    if (!rows.length) {{
      var empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'No notifications match. Try a different search term or filter.';
      listEl.appendChild(empty);
      return;
    }}

    var frag = document.createDocumentFragment();
    rows.forEach(function(item) {{
      var r = item.r, snap = item.snap;
      var key = 'browse::' + version + '::' + r.name;
      var article = document.createElement('article');
      article.className = 'entry';
      var isOpen = !!openState[key];
      article.dataset.open = isOpen ? 'true' : 'false';

      var head = document.createElement('button');
      head.className = 'entry-head';
      head.type = 'button';
      head.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

      var idWrap = document.createElement('div');
      idWrap.className = 'entry-id';
      var nameEl = document.createElement('span');
      nameEl.className = 'entry-name';
      nameEl.textContent = r.name;
      var sub = document.createElement('div');
      sub.className = 'entry-sub';
      var oidEl = document.createElement('span');
      oidEl.className = 'entry-oid';
      oidEl.textContent = snap.oid;
      sub.appendChild(oidEl);
      sub.appendChild(buildPresenceDots(r));
      idWrap.appendChild(nameEl);
      idWrap.appendChild(sub);

      var metaWrap = document.createElement('div');
      metaWrap.className = 'entry-meta';
      var badge = document.createElement('span');
      badge.className = 'badge ' + (snap.juniper_enterprise ? 'badge-enterprise' : 'badge-standard');
      badge.textContent = snap.juniper_enterprise ? 'Juniper' : 'Standard';
      metaWrap.appendChild(badge);
      if (r.os_scope !== 'Both') {{
        var osBadge = document.createElement('span');
        osBadge.className = 'badge badge-unchanged';
        osBadge.textContent = r.os_scope;
        metaWrap.appendChild(osBadge);
      }}
      if (item.decoded) {{
        var decodedBadge = document.createElement('span');
        decodedBadge.className = 'badge badge-decoded';
        decodedBadge.textContent = 'Decoded';
        metaWrap.appendChild(decodedBadge);
      }}
      var moduleEl = document.createElement('span');
      moduleEl.className = 'entry-module';
      moduleEl.textContent = snap.module;
      metaWrap.appendChild(moduleEl);
      metaWrap.appendChild(buildChevron());

      head.appendChild(idWrap);
      head.appendChild(metaWrap);

      var body = document.createElement('div');
      body.className = 'entry-body';
      body.appendChild(buildSnapshot(version, snap, null, null));
      var lifecycleNote = document.createElement('p');
      lifecycleNote.className = 'diff-note';
      var junosBit = r.present_junos.length ? 'Junos: ' + r.lifecycle_junos + ' (' + r.present_junos.join(', ') + ')' : 'Junos: not present';
      var evoBit = r.present_evo.length ? 'Junos-EVO: ' + r.lifecycle_evo + ' (' + r.present_evo.join(', ') + ')' : 'Junos-EVO: not present';
      lifecycleNote.textContent = junosBit + '  \\u00b7  ' + evoBit;
      body.appendChild(lifecycleNote);

      head.addEventListener('click', function() {{
        var nowOpen = article.dataset.open !== 'true';
        article.dataset.open = nowOpen ? 'true' : 'false';
        head.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
        openState[key] = nowOpen;
      }});

      article.appendChild(head);
      article.appendChild(body);
      frag.appendChild(article);
    }});
    listEl.appendChild(frag);
  }}

  // ============ COMPARE MODE ============
  function computeStatus(vFrom, vTo) {{
    if (vFrom.present && vTo.present) return snapshotsDiffer(vFrom, vTo) ? 'changed' : 'unchanged';
    if (!vFrom.present && vTo.present) return 'added';
    if (vFrom.present && !vTo.present) return 'removed';
    return null;
  }}

  function renderCompare() {{
    var q = q2El.value.trim().toLowerCase();
    var fromV = fromVersionEl.value;
    var toV = toVersionEl.value;
    var statusFilter = statusFilterEl.value;
    var category = category2El.value;

    var rows = [];
    registry.forEach(function(r) {{
      var vf = r.versions[fromV], vt = r.versions[toV];
      var status = computeStatus(vf, vt);
      if (!status) return;
      if (statusFilter === 'changes' && status === 'unchanged') return;
      if (statusFilter !== 'all' && statusFilter !== 'changes' && statusFilter !== status) return;
      if (category !== 'all' && r.category !== category) return;
      var repSnap = vt.present ? vt : vf;
      if (!matchesQuery(r.name, repSnap.module, repSnap.oid, repSnap.description, repSnap.objects_detail, q)) return;
      rows.push({{ r: r, vf: vf, vt: vt, status: status }});
    }});

    var order = {{ added: 0, removed: 1, changed: 2, unchanged: 3 }};
    rows.sort(function(a, b) {{
      return order[a.status] - order[b.status] || a.r.name.localeCompare(b.r.name);
    }});

    countEl.textContent = rows.length + (rows.length === 1 ? ' notification' : ' notifications') +
      ' between ' + fromV + ' \\u2192 ' + toV;

    listEl.innerHTML = '';
    if (!rows.length) {{
      var empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'No notifications match this comparison and filter combination.';
      listEl.appendChild(empty);
      return;
    }}

    var frag = document.createDocumentFragment();
    rows.forEach(function(item) {{
      var r = item.r, vf = item.vf, vt = item.vt, status = item.status;
      var repSnap = vt.present ? vt : vf;
      var key = 'compare::' + fromV + '::' + toV + '::' + r.name;
      var article = document.createElement('article');
      article.className = 'entry';
      var isOpen = !!openState[key];
      article.dataset.open = isOpen ? 'true' : 'false';

      var head = document.createElement('button');
      head.className = 'entry-head';
      head.type = 'button';
      head.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

      var idWrap = document.createElement('div');
      idWrap.className = 'entry-id';
      var nameEl = document.createElement('span');
      nameEl.className = 'entry-name';
      nameEl.textContent = r.name;
      var sub = document.createElement('div');
      sub.className = 'entry-sub';
      var oidEl = document.createElement('span');
      oidEl.className = 'entry-oid';
      oidEl.textContent = repSnap.oid;
      sub.appendChild(oidEl);
      idWrap.appendChild(nameEl);
      idWrap.appendChild(sub);

      var metaWrap = document.createElement('div');
      metaWrap.className = 'entry-meta';
      var statusBadge = document.createElement('span');
      statusBadge.className = 'badge badge-' + status;
      statusBadge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
      metaWrap.appendChild(statusBadge);
      var moduleEl = document.createElement('span');
      moduleEl.className = 'entry-module';
      moduleEl.textContent = repSnap.module;
      metaWrap.appendChild(moduleEl);
      metaWrap.appendChild(buildChevron());

      head.appendChild(idWrap);
      head.appendChild(metaWrap);

      var body = document.createElement('div');
      body.className = 'entry-body';

      if (status === 'unchanged') {{
        body.appendChild(buildSnapshot(fromV + ' \\u2192 ' + toV + ' (unchanged)', repSnap, null, null));
      }} else if (status === 'added') {{
        var note = document.createElement('p');
        note.className = 'diff-note';
        note.textContent = 'Not present in ' + fromV + '.';
        body.appendChild(note);
        body.appendChild(buildSnapshot('As of ' + toV, vt, null, null));
      }} else if (status === 'removed') {{
        var note2 = document.createElement('p');
        note2.className = 'diff-note';
        note2.textContent = 'No longer present in ' + toV + '.';
        body.appendChild(note2);
        body.appendChild(buildSnapshot('As of ' + fromV, vf, null, null));
      }} else {{
        var flagsFrom = [], flagsTo = [];
        if (vf.oid !== vt.oid) {{ flagsFrom.push('OID changed'); flagsTo.push('OID changed'); }}
        if (vf.description !== vt.description) {{ flagsFrom.push('description changed'); flagsTo.push('description changed'); }}
        if (varbindsText(vf.objects_detail) !== varbindsText(vt.objects_detail)) {{ flagsFrom.push('varbinds changed'); flagsTo.push('varbinds changed'); }}
        body.appendChild(buildSnapshot('As of ' + fromV, vf, flagsFrom, vt.objects_detail));
        body.appendChild(buildSnapshot('As of ' + toV, vt, flagsTo, vf.objects_detail));
      }}

      head.addEventListener('click', function() {{
        var nowOpen = article.dataset.open !== 'true';
        article.dataset.open = nowOpen ? 'true' : 'false';
        head.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
        openState[key] = nowOpen;
      }});

      article.appendChild(head);
      article.appendChild(body);
      frag.appendChild(article);
    }});
    listEl.appendChild(frag);
  }}

  function render() {{
    if (mode === 'browse') renderBrowse(); else renderCompare();
  }}
  function scheduleRender() {{
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(render, 100);
  }}

  modeBrowseBtn.addEventListener('click', function() {{
    mode = 'browse';
    modeBrowseBtn.setAttribute('aria-pressed', 'true');
    modeCompareBtn.setAttribute('aria-pressed', 'false');
    controlsBrowse.hidden = false;
    controlsCompare.hidden = true;
    render();
  }});
  modeCompareBtn.addEventListener('click', function() {{
    mode = 'compare';
    modeCompareBtn.setAttribute('aria-pressed', 'true');
    modeBrowseBtn.setAttribute('aria-pressed', 'false');
    controlsCompare.hidden = false;
    controlsBrowse.hidden = true;
    render();
  }});

  qEl.addEventListener('input', scheduleRender);
  q2El.addEventListener('input', scheduleRender);
  browseVersionEl.addEventListener('change', render);
  scopeEl.addEventListener('change', render);
  osScopeFilterEl.addEventListener('change', render);
  categoryEl.addEventListener('change', render);
  decodedEl.addEventListener('change', render);
  sortEl.addEventListener('change', render);
  fromVersionEl.addEventListener('change', render);
  toVersionEl.addEventListener('change', render);
  statusFilterEl.addEventListener('change', render);
  category2El.addEventListener('change', render);

  render();
}})();
</script>
"""

out_path = SNMP_ROOT / "juniper_trap_catalog.html"
out_path.write_text(html)
print(f"Wrote {out_path} ({len(html)} chars)")
