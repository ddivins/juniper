import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from srx_idp.download import build_update_url, download_update


class DownloadTests(unittest.TestCase):
    def test_url_targets_pack_and_omits_serial_by_default(self):
        query = parse_qs(urlparse(build_update_url("3702")).query, keep_blank_values=True)
        self.assertEqual(["3702"], query["to"])
        self.assertEqual(["update"], query["type"])
        self.assertNotIn("sn", query)

    def test_url_includes_serial_when_given(self):
        query = parse_qs(urlparse(build_update_url("latest", serial="ABC123")).query)
        self.assertEqual(["ABC123"], query["sn"])

    def test_download_decompresses_and_removes_archive(self):
        response = Mock(content=gzip.compress(b"<SignatureUpdate/>"))
        with tempfile.TemporaryDirectory() as tmp, patch("srx_idp.download.requests.get", return_value=response):
            path = download_update("http://x", Path(tmp), "offline-update-latest")
            self.assertEqual(b"<SignatureUpdate/>", path.read_bytes())
            self.assertFalse((Path(tmp) / "offline-update-latest.tgz").exists())


if __name__ == "__main__":
    unittest.main()
