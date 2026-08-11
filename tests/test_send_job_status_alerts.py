from __future__ import annotations

import json
import unittest
from io import BytesIO
from urllib.error import HTTPError

from src import send_job_status_alerts


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class TelegramSendTests(unittest.TestCase):
    def test_build_message_replaces_corrupted_question_mark_fields(self) -> None:
        message = send_job_status_alerts.build_message(
            {
                "kind": "manual",
                "company": "????? ????",
                "title": "קניינית רכש",
                "score": "84",
                "link": "https://example.com/job",
                "matched_requirements": "?????, Excel, ???",
                "company_info": "מיקום: ????",
                "blocker": "????? ???? ?????",
                "recommendation": "????? ?????",
            }
        )

        self.assertIn("נדרשת הגשה עצמאית", message)
        self.assertIn("חברה לא זמינה בגלל בעיית קידוד במקור", message)
        self.assertIn("דרישות לא זמינות בגלל בעיית קידוד במקור", message)
        self.assertNotIn("????", message)

    def test_send_blocks_prebuilt_corrupted_text_before_api_call(self) -> None:
        original_urlopen = send_job_status_alerts.urlopen

        def fake_urlopen(request, timeout):
            raise AssertionError("urlopen should not be called for corrupted Telegram text")

        try:
            send_job_status_alerts.urlopen = fake_urlopen
            with self.assertRaises(ValueError):
                send_job_status_alerts.send("token", "-1001", "כותרת\n????")
        finally:
            send_job_status_alerts.urlopen = original_urlopen

    def test_send_retries_with_migrated_supergroup_chat_id(self) -> None:
        calls: list[str] = []
        original_urlopen = send_job_status_alerts.urlopen

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            calls.append(str(payload["chat_id"]))
            if len(calls) == 1:
                body = {
                    "ok": False,
                    "error_code": 400,
                    "description": "Bad Request: group chat was upgraded to a supergroup chat",
                    "parameters": {"migrate_to_chat_id": -1009999999999},
                }
                raise HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    hdrs=None,
                    fp=BytesIO(json.dumps(body).encode("utf-8")),
                )
            return _FakeResponse({"ok": True, "result": {"message_id": 123}})

        try:
            send_job_status_alerts.urlopen = fake_urlopen
            result = send_job_status_alerts.send("token", "-999999999", "hello")
        finally:
            send_job_status_alerts.urlopen = original_urlopen

        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["-999999999", "-1009999999999"])
        self.assertEqual(result["_migrated_to_chat_id"], "-1009999999999")


if __name__ == "__main__":
    unittest.main()
