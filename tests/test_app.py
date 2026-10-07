import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as dashboard


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.drafts_path = self.root / "drafts.json"
        self.capsule_dir = self.root / "capsule"
        self.csv_path = self.root / "question_bank.csv"
        with self.csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["subject", "topic", "question", "exam", "year", "source_file"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "subject": "Anatomy",
                    "topic": "Ulnar nerve",
                    "question": "Which muscles are supplied by the ulnar nerve?",
                    "exam": "INI-CET",
                    "year": "2025",
                    "source_file": "chapterwise.txt",
                }
            )

        self.paths_patch = patch.multiple(
            dashboard,
            DRAFTS_PATH=self.drafts_path,
            CAPSULE_DIR=self.capsule_dir,
        )
        self.paths_patch.start()
        self.csv_patch = patch.object(dashboard, "csv_path", return_value=self.csv_path)
        self.csv_patch.start()
        self.addCleanup(self.csv_patch.stop)
        self.addCleanup(self.paths_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)
        dashboard.app.testing = True
        self.client = dashboard.app.test_client()

    @staticmethod
    def valid_payload(**overrides):
        payload = {
            "subject": "Anatomy",
            "topic": "Ulnar nerve",
            "clinical_stem": "Which intrinsic hand muscles are supplied by this nerve?",
            "core_concept": "It supplies all intrinsic hand muscles except the LOAF group.",
            "confidence": "Low",
            "frequency": "Seen in PYQs",
            "source": "Doctutorial mock 1",
        }
        payload.update(overrides)
        return payload

    def save_draft(self, **overrides):
        return self.client.post("/api/drafts", json=self.valid_payload(**overrides))

    def test_dashboard_serves_manual_entry_form(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Approve &amp; Publish", response.data)
        self.assertIn(b"Core concept / trap", response.data)
        self.assertIn(b'option value="General Medicine"', response.data)
        self.assertIn(b"Use in note & preview", response.data)

    def test_legacy_draft_payload_saves_with_markdown_field_order(self):
        response = self.client.post(
            "/api/draft",
            json={
                "subject": "General Medicine",
                "topic": "Blood supply of the heart",
                "stem": "Which arteries supply the SA and AV nodes?",
                "concept": "The right coronary artery supplies both nodes in most people.",
                "confidence": "Med",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["success"])
        self.assertEqual(response.json["clinical_stem"], "Which arteries supply the SA and AV nodes?")
        self.assertEqual(response.json["core_concept"], "The right coronary artery supplies both nodes in most people.")
        self.assertEqual(response.json["frequency"], "Not sure")

        published = self.client.post(f"/api/drafts/{response.json['id']}/publish")
        self.assertEqual(published.status_code, 200)
        contents = (self.capsule_dir / "general-medicine.md").read_text(encoding="utf-8")
        self.assertLess(contents.index("Clinical stem / question"), contents.index("Core concept / trap"))
        self.assertLess(contents.index("Core concept / trap"), contents.index("Confidence"))

    def test_csv_search_finds_related_question(self):
        response = self.client.get("/api/search?q=ulnar")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["results"][0]["topic"], "Ulnar nerve")
        self.assertEqual(response.json["results"][0]["year"], "2025")

    def test_approval_is_required_before_note_is_published(self):
        saved = self.save_draft()
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json["status"], "Draft")
        self.assertFalse(self.capsule_dir.exists())

        published = self.client.post(f"/api/drafts/{saved.json['id']}/publish")
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json["status"], "Published")
        note_file = self.capsule_dir / "anatomy.md"
        note_contents = note_file.read_text(encoding="utf-8")
        self.assertIn("### Ulnar nerve", note_contents)
        self.assertIn("LOAF group", note_contents)

        drafts = json.loads(self.drafts_path.read_text(encoding="utf-8"))["drafts"]
        self.assertEqual(drafts[0]["status"], "Published")

    def test_published_draft_cannot_be_published_twice(self):
        saved = self.save_draft()
        draft_id = saved.json["id"]
        self.assertEqual(self.client.post(f"/api/drafts/{draft_id}/publish").status_code, 200)
        duplicate = self.client.post(f"/api/drafts/{draft_id}/publish")
        self.assertEqual(duplicate.status_code, 409)
        contents = (self.capsule_dir / "anatomy.md").read_text(encoding="utf-8")
        self.assertEqual(contents.count(f"<!-- nuclear-note-id:{draft_id} -->"), 1)

    def test_saved_draft_can_be_edited_before_publication(self):
        saved = self.save_draft()
        updated = self.client.post(
            "/api/drafts",
            json=self.valid_payload(id=saved.json["id"], topic="Ulnar nerve injury"),
        )
        self.assertEqual(updated.status_code, 201)
        self.assertEqual(updated.json["id"], saved.json["id"])
        self.assertEqual(len(self.client.get("/api/drafts").json), 1)
        self.assertEqual(updated.json["topic"], "Ulnar nerve injury")

    def test_invalid_draft_is_rejected(self):
        response = self.client.post("/api/drafts", json=self.valid_payload(confidence="Certain"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Confidence", response.json["error"])


if __name__ == "__main__":
    unittest.main()
