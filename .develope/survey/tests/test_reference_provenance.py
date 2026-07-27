from __future__ import annotations

import sys
import io
import json
import unittest
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.reference import (
    LEGACY_SOURCE_COMMITS,
    build_legacy_reference_manifest,
    validate_legacy_source_paths,
)
from dcsmizzer_survey.cli import main


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_DATA = REPOSITORY_ROOT / ".develope" / "reference" / "data"
UPSTREAM_ROOT = REPOSITORY_ROOT / ".develope" / "upstream"


class ReferenceProvenanceTests(unittest.TestCase):
    def test_every_legacy_data_file_has_source_project_paths_and_frozen_commit(self) -> None:
        # Would fail when a new snapshot silently appears without provenance.
        manifest = build_legacy_reference_manifest(REFERENCE_DATA)
        actual_files = {
            path.name
            for path in REFERENCE_DATA.iterdir()
            if path.is_file()
        }

        self.assertEqual(
            {dataset["path"] for dataset in manifest["datasets"]},
            actual_files,
        )
        self.assertEqual(manifest["unmapped"], [])
        for dataset in manifest["datasets"]:
            self.assertEqual(dataset["status"], "legacy_frozen")
            self.assertEqual(dataset["extractor"], "legacy-one-off/unavailable")
            self.assertEqual(len(dataset["sha256"]), 64)
            self.assertGreater(dataset["bytes"], 0)
            self.assertTrue(dataset["sources"])
            for source in dataset["sources"]:
                self.assertTrue(source["paths"])
                self.assertEqual(
                    source["commit"],
                    LEGACY_SOURCE_COMMITS[source["project"]],
                )

    def test_retribution_snapshot_is_bound_to_commit_matching_legacy_counts(self) -> None:
        # Would fail if current Retribution HEAD is mislabeled as the old extract.
        manifest = build_legacy_reference_manifest(REFERENCE_DATA)
        datasets = {item["path"]: item for item in manifest["datasets"]}
        source = datasets["retribution-factions-index.json"]["sources"][0]

        self.assertEqual(source["project"], "retribution")
        self.assertEqual(
            source["commit"],
            "b7493d016f3c2c65d3a1ba73efdf0861d9c2dd7e",
        )
        self.assertIn("resources/factions/*.json", source["paths"])

    def test_every_declared_legacy_source_path_exists_at_its_frozen_commit(self) -> None:
        # Would fail if provenance contains a plausible but invented source path.
        manifest = build_legacy_reference_manifest(REFERENCE_DATA)
        repositories = {
            "briefing_room": UPSTREAM_ROOT / "briefing-room-for-dcs",
            "gtd": UPSTREAM_ROOT / "dcs-global-terrain-database",
            "mission_maker": UPSTREAM_ROOT / "dcs-mission-maker",
            "retribution": UPSTREAM_ROOT / "dcs-retribution",
            "moose": UPSTREAM_ROOT / "MOOSE",
            "pydcs": UPSTREAM_ROOT / "pydcs",
        }

        missing = validate_legacy_source_paths(manifest, repositories)

        self.assertEqual(missing, [])

    def test_cli_legacy_reference_emits_validated_manifest(self) -> None:
        # Would fail if provenance can be generated without validating source paths.
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            [
                "legacy-reference",
                "--data-root",
                str(REFERENCE_DATA),
                "--upstream-root",
                str(UPSTREAM_ROOT),
            ],
            stdout=stdout,
            stderr=stderr,
        )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            report["schema"],
            "dcsmizzer.reference-provenance/v1",
        )
        self.assertEqual(report["source_path_errors"], [])


if __name__ == "__main__":
    unittest.main()
