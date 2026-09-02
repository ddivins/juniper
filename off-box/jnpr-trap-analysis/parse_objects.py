#!/usr/bin/env python3
"""Library module: index OBJECT-TYPE and TEXTUAL-CONVENTION definitions in a
single MIB text file and resolve enumerated INTEGER/BITS SYNTAX values.
Used by build_full_catalog.py - not meant to be run directly."""
import re
from pathlib import Path

def clean_ws(s):
    return re.sub(r"\s+", " ", s).strip()

def find_matching_brace(text, open_idx):
    """text[open_idx] must be '{'. Return index of matching '}'."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1

ENUM_ITEM_RE = re.compile(r"([A-Za-z][A-Za-z0-9-]*)\s*\(\s*(-?\d+)\s*\)")

def extract_enum_after_syntax(text, syntax_kw_idx):
    """Given index right after the word 'SYNTAX', look for INTEGER{...} or
    BITS{...} and return (kind, {value:label}, end_idx) or (base_type_token, None, end_idx)."""
    rest = text[syntax_kw_idx:syntax_kw_idx + 4000]  # bounded lookahead
    m = re.match(r"\s*(INTEGER|BITS)\s*\{", rest)
    if m:
        brace_open = syntax_kw_idx + m.end() - 1
        brace_close = find_matching_brace(text, brace_open)
        if brace_close == -1:
            return m.group(1), None, syntax_kw_idx + m.end()
        body = text[brace_open + 1:brace_close]
        enum = {int(v): label for label, v in ENUM_ITEM_RE.findall(body)}
        return m.group(1), enum, brace_close + 1
    # not an inline enum - grab the first token as the base type name
    m2 = re.match(r"\s*([A-Za-z][A-Za-z0-9-]*)", rest)
    if m2:
        return m2.group(1), None, syntax_kw_idx + m2.end()
    return None, None, syntax_kw_idx

MODULE_NAME_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s+DEFINITIONS\b", re.MULTILINE)

TC_HEADER_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*::=\s*TEXTUAL-CONVENTION\b", re.MULTILINE)
OBJTYPE_HEADER_RE = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9]*)\s+OBJECT-TYPE\s*$", re.MULTILINE)
DESCRIPTION_RE = re.compile(r'DESCRIPTION\s*"(.*?)"', re.DOTALL)

def parse_file(path: Path):
    text = path.read_text(errors="replace")
    m = MODULE_NAME_RE.search(text)
    module = m.group(1) if m else path.stem

    tcs = {}
    for hm in TC_HEADER_RE.finditer(text):
        name = hm.group(1)
        window_end = min(len(text), hm.end() + 6000)
        window = text[hm.end():window_end]
        syn = re.search(r"\bSYNTAX\b", window)
        if not syn:
            continue
        base, enum, _ = extract_enum_after_syntax(window, syn.end())
        tcs[name] = {"base": base, "enum": enum, "module": module, "file": path.name}

    objs = {}
    for hm in OBJTYPE_HEADER_RE.finditer(text):
        name = hm.group(1)
        window_end = min(len(text), hm.end() + 6000)
        window = text[hm.end():window_end]
        syn = re.search(r"\bSYNTAX\b", window)
        if not syn:
            continue
        base, enum, after_idx = extract_enum_after_syntax(window, syn.end())
        desc_m = DESCRIPTION_RE.search(window)
        desc = clean_ws(desc_m.group(1)) if desc_m else ""
        objs[name] = {"base": base, "enum": enum, "module": module, "file": path.name, "description": desc}

    return module, tcs, objs
