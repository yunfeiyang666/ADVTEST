import tempfile
import unittest
from pathlib import Path

from patch_llamafactory_minicpmo import MARKER, ORIGINAL, apply_patch


class MiniCPMOPatchTests(unittest.TestCase):
    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collator = Path(temp_dir) / "collator.py"
            collator.write_text("prefix\n" + ORIGINAL + "suffix\n", encoding="utf-8")
            self.assertEqual(apply_patch(collator), "patched")
            self.assertIn(MARKER, collator.read_text(encoding="utf-8"))
            self.assertEqual(apply_patch(collator), "already_patched")


if __name__ == "__main__":
    unittest.main()
