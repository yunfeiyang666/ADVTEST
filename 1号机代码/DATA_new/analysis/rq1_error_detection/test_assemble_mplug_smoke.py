import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from assemble_mplug_smoke import assemble_suites


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AssembleMPLUGSmokeTests(unittest.TestCase):
    def test_assembles_exact_prefix_without_modifying_records_and_hashes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = {}
            expected = {}
            for method in (
                "advtest",
                "random",
                "official_qa",
                "qatest_adapted",
            ):
                records = [
                    {
                        "question": f"{method} question {index}",
                        "answer": "car",
                        "vlm_call_cost": 1,
                    }
                    for index in range(3)
                ]
                path = root / f"{method}-source.jsonl"
                path.write_text(
                    "".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8",
                )
                sources[method] = path
                expected[method] = records[:2]

            output_dir = root / "assembled"
            manifest = assemble_suites(sources, output_dir, call_budget=2)

            self.assertEqual(set(manifest["suites"]), set(sources))
            for method, source in sources.items():
                output = output_dir / f"{method}_suite.jsonl"
                actual = [
                    json.loads(line)
                    for line in output.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(actual, expected[method])
                self.assertEqual(
                    manifest["suites"][method]["source_sha256"],
                    sha256(source),
                )
                self.assertEqual(
                    manifest["suites"][method]["output_sha256"],
                    sha256(output),
                )
                self.assertEqual(manifest["suites"][method]["calls"], 2)

            saved = json.loads(
                (output_dir / "assembly_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, manifest)

    def test_rejects_non_empty_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps(
                    {"question": "What is visible?", "answer": "car"}
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "assembled"
            output_dir.mkdir()
            (output_dir / "existing.txt").write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "not empty"):
                assemble_suites({"advtest": source}, output_dir, call_budget=1)

            self.assertEqual(
                (output_dir / "existing.txt").read_text(encoding="utf-8"),
                "keep",
            )

    def test_rejects_source_that_cannot_reach_call_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "question": "What is visible?",
                        "answer": "car",
                        "vlm_call_cost": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "only provides 1 calls"):
                assemble_suites(
                    {"advtest": source},
                    root / "assembled",
                    call_budget=2,
                )


if __name__ == "__main__":
    unittest.main()
