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
            json.dumps({"FLOTA": ["fleet-user"], "RESPONSABLE": ["fallback-user"]}),
            encoding="utf-8",
        )

        with patch.object(alert_router, "_CONFIG_PATH", self._config_path):
            recipients = alert_router.resolve_recipients(
                "ITV_EXPIRED",
                direct_target="driver-user",
            )

        self.assertEqual(recipients, ["driver-user", "fleet-user"])

    def test_env_values_extend_project_config_without_duplicates(self) -> None:
        self._config_path.write_text(
            json.dumps({"COMPRAS": ["compras-1"]}),
            encoding="utf-8",
        )

        with patch.object(alert_router, "_CONFIG_PATH", self._config_path):
            with patch.dict(os.environ, {"ALERT_ROLE_COMPRAS": "compras-1,compras-2"}):
                routing = alert_router.get_routing_context("LICENSE_EXPIRING")

        self.assertEqual(routing["roles"], ["COMPRAS"])
        self.assertEqual(routing["role_targets"], {"COMPRAS": ["compras-1", "compras-2"]})
        self.assertEqual(routing["recipients"], ["compras-1", "compras-2"])


if __name__ == "__main__":
    unittest.main()
