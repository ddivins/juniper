import os
import unittest
from unittest.mock import patch

from srx_idp.device import connection_parameters


class DeviceSettingsTests(unittest.TestCase):
    def test_builds_key_connection(self):
        values = {
            "SRX_HOSTNAME": "192.0.2.1",
            "SRX_USERNAME": "automation",
            "SRX_SSH_KEY": "~/.ssh/test-key",
        }
        with patch.dict(os.environ, values, clear=True):
            params = connection_parameters()
        self.assertEqual("192.0.2.1", params["host"])
        self.assertEqual(22, params["port"])
        self.assertNotIn("password", params)

    def test_requires_authentication(self):
        with patch.dict(os.environ, {"SRX_HOSTNAME": "host", "SRX_USERNAME": "user"}, clear=True):
            with self.assertRaises(ValueError):
                connection_parameters()


if __name__ == "__main__":
    unittest.main()

