from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend import cli
from backend.catalog_export import render_model_metadata_list


class CatalogExportTests(unittest.TestCase):
    def test_render_jsonl_prints_one_complete_model_per_line(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "scores": {"benchmark": {"value": 95.0, "verified": True}},
                "inference_destinations": [{"id": "aws-bedrock", "regions": ["us-east-1"]}],
            },
            {
                "id": "model-b",
                "name": "Model B",
                "provider": "Provider",
                "license_id": "apache-2.0",
            },
        ]

        rendered = render_model_metadata_list(models, output_format="jsonl")

        lines = rendered.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), models[0])
        self.assertEqual(json.loads(lines[1]), models[1])

    def test_render_csv_flattens_nested_metadata(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "scores": {"benchmark": {"value": 95.0, "verified": True}},
                "inference_destinations": [{"id": "aws-bedrock", "regions": ["us-east-1"]}],
            }
        ]

        rendered = render_model_metadata_list(models, output_format="csv")

        rows = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(rows[0]["id"], "model-a")
        self.assertEqual(json.loads(rows[0]["scores"]), models[0]["scores"])
        self.assertEqual(json.loads(rows[0]["inference_destinations"]), models[0]["inference_destinations"])

    def test_cli_list_models_writes_output_file(self) -> None:
        models = [{"id": "model-a", "name": "Model A", "provider": "Provider"}]

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "models.json"
            stdout = io.StringIO()

            with patch("backend.cli.build_model_metadata_list", return_value=models), redirect_stdout(stdout):
                exit_code = cli.main(["list-models", "--output", str(output_path), "--no-csv"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), models)
            self.assertIn("Exported 1 models", stdout.getvalue())

    def test_cli_list_models_writes_default_csv_sidecar(self) -> None:
        models = [{"id": "model-a", "name": "Model A", "provider": "Provider"}]

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "models.json"
            csv_output_path = Path(tempdir) / "model-list.csv"
            stdout = io.StringIO()

            with patch("backend.cli.build_model_metadata_list", return_value=models), redirect_stdout(stdout):
                exit_code = cli.main(
                    [
                        "list-models",
                        "--output",
                        str(output_path),
                        "--csv-output",
                        str(csv_output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), models)
            self.assertEqual(csv_output_path.read_text(encoding="utf-8"), "id,name,provider\nmodel-a,Model A,Provider\n")
            self.assertIn("Exported CSV sidecar", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
