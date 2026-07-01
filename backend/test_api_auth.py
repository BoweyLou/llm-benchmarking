from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class ApiAdminGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_token = os.environ.get(main.ADMIN_TOKEN_ENV_VAR)
        os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)

    def tearDown(self) -> None:
        if self.original_token is None:
            os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        else:
            os.environ[main.ADMIN_TOKEN_ENV_VAR] = self.original_token

    def test_read_route_remains_available_without_admin_token(self) -> None:
        with patch("backend.main.bootstrap"), patch("backend.main.list_benchmarks", return_value=[]):
            response = TestClient(main.app).get("/api/benchmarks")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_mutating_route_is_disabled_without_configured_admin_token(self) -> None:
        with patch("backend.main.bootstrap"), patch("backend.main.schedule_update") as schedule_update:
            response = TestClient(main.app).post("/api/update", json={})

        self.assertEqual(response.status_code, 403)
        self.assertIn(main.ADMIN_TOKEN_ENV_VAR, response.json()["detail"])
        schedule_update.assert_not_called()

    def test_mutating_route_rejects_missing_or_invalid_admin_token(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"

        with patch("backend.main.bootstrap"), patch("backend.main.schedule_update") as schedule_update:
            client = TestClient(main.app)
            missing = client.post("/api/update", json={})
            invalid = client.post(
                "/api/update",
                json={},
                headers={main.ADMIN_TOKEN_HEADER: "wrong-token"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        schedule_update.assert_not_called()

    def test_mutating_route_accepts_header_admin_token(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"

        with patch("backend.main.bootstrap"), patch("backend.main.schedule_update", return_value=42) as schedule_update:
            response = TestClient(main.app).post(
                "/api/update",
                json={},
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"log_id": 42, "status": "running"})
        schedule_update.assert_called_once_with(benchmarks=None, triggered_by="api")

    def test_mutating_route_accepts_bearer_admin_token(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"

        with patch("backend.main.bootstrap"), patch("backend.main.schedule_update", return_value=43) as schedule_update:
            response = TestClient(main.app).post(
                "/api/update",
                json={},
                headers={"Authorization": "Bearer secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"log_id": 43, "status": "running"})
        schedule_update.assert_called_once_with(benchmarks=None, triggered_by="api")


if __name__ == "__main__":
    unittest.main()
