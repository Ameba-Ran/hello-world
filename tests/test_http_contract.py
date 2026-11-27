"""The public example's HTTP responses must match its SDK results."""

import unittest
from unittest.mock import Mock, patch

from ameba_sdk import AmebaError
from fastapi.testclient import TestClient

import main


class HttpContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_models_success(self) -> None:
        ai = Mock()
        ai.llm.models.return_value = ["ameba/chat"]
        with patch.object(main, "_ai", return_value=ai):
            response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"models": ["ameba/chat"]})

    def test_models_upstream_failure(self) -> None:
        ai = Mock()
        ai.llm.models.side_effect = AmebaError("gateway unavailable")
        with patch.object(main, "_ai", return_value=ai):
            response = self.client.get("/models")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "gateway unavailable"})

    def test_speak_returns_mp3_with_matching_content_type(self) -> None:
        ai = Mock()
        ai.tts.speak.return_value = b"ID3mock-mp3"
        with patch.object(main, "_ai", return_value=ai):
            response = self.client.post("/speak", json={"prompt": "Hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.content, b"ID3mock-mp3")
        ai.tts.speak.assert_called_once_with("Hello", response_format="mp3")

    def test_speak_upstream_failure(self) -> None:
        ai = Mock()
        ai.tts.speak.side_effect = AmebaError("speech unavailable")
        with patch.object(main, "_ai", return_value=ai):
            response = self.client.post("/speak", json={"prompt": "Hello"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "speech unavailable"})


if __name__ == "__main__":
    unittest.main()
