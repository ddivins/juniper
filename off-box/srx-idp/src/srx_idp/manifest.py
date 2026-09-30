from __future__ import annotations

from pathlib import Path

from lxml import etree


def load_entries(path: Path) -> dict[str, bytes]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
    entries: dict[str, bytes] = {}
    for entry in tree.xpath("/SignatureUpdate/Entries/Entry"):
        names = entry.xpath("Name/text()")
        if names:
            entries[str(names[0])] = etree.tostring(entry, method="c14n")
    return entries


def changed_entries(old_path: Path, new_path: Path) -> list[str]:
    old = load_entries(old_path)
    new = load_entries(new_path)
    return sorted(name for name, value in new.items() if old.get(name) != value)



def removed_entries(old_path: Path, new_path: Path) -> list[str]:
    """Entry names present in the older pack but absent from the newer one (retired signatures)."""
    return sorted(set(load_entries(old_path)) - set(load_entries(new_path)))


def pack_names(path: Path) -> set[str]:
    return set(load_entries(path))
