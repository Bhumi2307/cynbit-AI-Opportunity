import unittest

from app import app, triage_assistant


class AiTriageEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_suggests_category_priority_and_team(self):
        response = self.client.post(
            "/api/ai/triage",
            json={"Description": "The wireless network is unavailable for everyone in the office"},
        )

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["suggested_issue_type"], "wifi")
        self.assertEqual(result["suggested_priority"], "high")
        self.assertEqual(result["suggested_team"], "Network")
        self.assertFalse(result["auto_action"])
        self.assertEqual(result["decision_basis"], "urgent_signal_override")

    def test_requires_non_empty_description(self):
        response = self.client.post("/api/ai/triage", json={"Description": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Description", response.get_json()["error"])

    def test_suggests_each_supported_category_and_existing_team(self):
        cases = [
            ("wireless network keeps disconnecting", "wifi", "Network"),
            ("locked out and cannot sign in to my account", "login", "IT Support"),
            ("application crashes when I open a report", "software", "Applications"),
            ("laptop screen is broken and keyboard stopped working", "hardware", "Infrastructure"),
            ("how can I update my profile display name", "other", "General"),
        ]
        for description, category, team in cases:
            with self.subTest(category=category):
                result = triage_assistant.predict(description)
                self.assertEqual(result["suggested_issue_type"], category)
                self.assertEqual(result["suggested_team"], team)
                self.assertFalse(result["auto_action"])

    def test_suggests_priority_for_representative_examples(self):
        cases = [
            ("please order a keyboard for a new team member", "low"),
            ("the office printer is jammed and multiple teams need it", "medium"),
            ("a bug in the latest release prevents invoice export", "high"),
        ]
        for description, priority in cases:
            with self.subTest(priority=priority):
                result = triage_assistant.predict(description)
                self.assertEqual(result["suggested_priority"], priority)

    def test_rejects_oversized_description(self):
        response = self.client.post("/api/ai/triage", json={"Description": "x" * 4001})

        self.assertEqual(response.status_code, 400)
        self.assertIn("4000", response.get_json()["error"])

    def test_rejects_non_json_request(self):
        response = self.client.post("/api/ai/triage", data="not json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "A JSON object is required"})

    def test_rejects_non_object_payload(self):
        response = self.client.post("/api/ai/triage", json=["not", "an", "object"])

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
