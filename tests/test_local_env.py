from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.local_env import load_local_env


class LocalEnvTests(unittest.TestCase):
    def test_load_local_env_sets_missing_values_without_overriding_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "TELEGRAM_BOT_TOKEN=from-file",
                        'TELEGRAM_CHAT_ID="-100123"',
                        "EXISTING_VALUE=file-value",
                    ]
                ),
                encoding="utf-8",
            )
            old_env = os.environ.copy()
            try:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("TELEGRAM_CHAT_ID", None)
                os.environ["EXISTING_VALUE"] = "already-set"

                load_local_env(env_path)

                self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "from-file")
                self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "-100123")
                self.assertEqual(os.environ["EXISTING_VALUE"], "already-set")
            finally:
                os.environ.clear()
                os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
