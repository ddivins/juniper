import unittest

import srx_idp_signature_delta_xls as compatibility_script


class CompatibilityScriptTests(unittest.TestCase):
    def test_rejects_missing_pack(self):
        self.assertEqual(1, compatibility_script.main([]))

    def test_rejects_non_integer_pack(self):
        self.assertEqual(1, compatibility_script.main(["not-a-number"]))

    def test_rejects_unknown_mode(self):
        self.assertEqual(1, compatibility_script.main(["3741", "online-ish"]))


if __name__ == "__main__":
    unittest.main()
