import tempfile
import unittest
from pathlib import Path

from srx_idp.manifest import changed_entries, removed_entries


def pack(entries: dict[str, str]) -> str:
    body = "".join(f"<Entry><Name>{n}</Name><Severity>{v}</Severity></Entry>" for n, v in entries.items())
    return f"<SignatureUpdate><Entries>{body}</Entries></SignatureUpdate>"


class ManifestTests(unittest.TestCase):
    def test_reports_removed_changed_and_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            old.write_text(pack({"KEEP": "Major", "GONE": "Minor", "EDIT": "Minor"}))
            new.write_text(pack({"KEEP": "Major", "EDIT": "Major", "NEW": "Info"}))
            self.assertEqual(["GONE"], removed_entries(old, new))
            self.assertEqual(["EDIT", "NEW"], changed_entries(old, new))


if __name__ == "__main__":
    unittest.main()
