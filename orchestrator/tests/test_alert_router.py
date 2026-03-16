import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import alert_router


class AlertRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_root = Path(__file__).resolve().parent / "_tmp"
        self._tmp_root.mkdir(exist_ok=True)
        self._config_path = self._tmp_root / "alert_roles.json"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_resolve_recipients_uses_project_config_and_direct_target(self) -> None:
        self._config_path.write_text(
            json.dumps(
                {
                    "FLOTA": {
                        "teamsUserIds": ["fleet-user"],
                        "emails": ["flota@empresa.com"],
                    },
                    "RESPONSABLE": ["fallback-user"],
                }
            ),
            encoding="utf-8",
        )

        with patch.object(alert_router, "_CONFIG_PATH", self._config_path):
            routing = alert_router.get_routing_context(
                "ITV_EXPIRED",
                direct_target="driver-user",
                direct_target_email="driver@empresa.com",
            )

        self.assertEqual(routing["recipients"], ["driver-user", "fleet-user"])
        self.assertEqual(routing["recipient_emails"], ["driver@empresa.com", "flota@empresa.com"])

    def test_env_values_extend_project_config_without_duplicates(self) -> None:
        self._config_path.write_text(
            json.dumps({"COMPRAS": {"teamsUserIds": ["compras-1"], "emails": ["compras@empresa.com"]}}),
            encoding="utf-8",
        )

        with patch.object(alert_router, "_CONFIG_PATH", self._config_path):
            with patch.dict(
                os.environ,
                {
                    "ALERT_ROLE_COMPRAS": "compras-1,compras-2",
                    "ALERT_ROLE_COMPRAS_EMAILS": "compras@empresa.com,compras2@empresa.com",
                },
            ):
                routing = alert_router.get_routing_context("LICENSE_EXPIRING")

        self.assertEqual(routing["roles"], ["COMPRAS"])
        self.assertEqual(routing["role_targets"], {"COMPRAS": ["compras-1", "compras-2"]})
        self.assertEqual(routing["role_emails"], {"COMPRAS": ["compras@empresa.com", "compras2@empresa.com"]})
        self.assertEqual(routing["recipients"], ["compras-1", "compras-2"])
        self.assertEqual(routing["recipient_emails"], ["compras@empresa.com", "compras2@empresa.com"])


if __name__ == "__main__":
    unittest.main()
