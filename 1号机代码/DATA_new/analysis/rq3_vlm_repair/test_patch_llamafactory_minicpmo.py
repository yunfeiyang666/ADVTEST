import tempfile
import unittest
from pathlib import Path

from patch_llamafactory_minicpmo import (
    BATCH_ENCODING_MARKER,
    HELPER_ANCHOR,
    IMPORT_ORIGINAL,
    MARKER,
    MM_INPUTS_ORIGINAL,
    MM_INPUTS_PATCHED,
    ORIGINAL,
    apply_patch,
)


class MiniCPMOPatchTests(unittest.TestCase):
    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collator = Path(temp_dir) / "collator.py"
            collator.write_text(
                IMPORT_ORIGINAL + "prefix\n" + ORIGINAL + HELPER_ANCHOR + "\n" + MM_INPUTS_ORIGINAL + "suffix\n",
                encoding="utf-8",
            )
            self.assertEqual(apply_patch(collator), "patched")
            patched = collator.read_text(encoding="utf-8")
            self.assertIn(MARKER, patched)
            self.assertIn(BATCH_ENCODING_MARKER, patched)
            self.assertIn(MM_INPUTS_PATCHED.strip(), patched)
            self.assertEqual(apply_patch(collator), "already_patched")


if __name__ == "__main__":
    unittest.main()
