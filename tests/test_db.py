"""Contract tests for the persistent service. Uses temporary, isolated databases."""
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petcare.db import Store


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "nested" / "demo.sqlite"
        self.store = Store(self.path)
        self.addCleanup(lambda: self.store.close())
        self.store.register("Балнұр", "BALNUR@example.test", "student-pass")
        self.session = self.store.login("balnur@example.test", "student-pass")

    def test_reopen_edit_seed_once_and_cascade_delete(self):
        self.store.seed_demo(self.session)
        pets = self.store.list_pets(self.session, sort="id")
        self.assertEqual(10, len(pets))
        luna = pets[0]
        self.store.save_pet(self.session, {"weight_kg": "4,3"}, luna["id"])
        self.store.close()
        self.store = Store(self.path)
        self.store.seed_demo(self.session)
        self.assertEqual(4.3, self.store.get_pet(self.session, luna["id"])["weight_kg"])
        self.assertEqual(10, len(self.store.list_pets(self.session)))
        self.assertEqual(4, len(self.store.list_pets(self.session, species="МЫСЫҚ")))
        self.assertEqual(1, len(self.store.list_pets(self.session, query="lUnA")))
        self.assertEqual(0, len(self.store.list_pets(self.session, query="%")))
        self.store.delete_pet(self.session, luna["id"])
        self.store.seed_demo(self.session)
        self.assertEqual(9, len(self.store.list_pets(self.session)))
        self.assertFalse(any(t["pet_id"] == luna["id"] for t in self.store.tasks(self.session)))

    def test_owner_isolation_across_services(self):
        self.store.seed_demo(self.session)
        luna = self.store.list_pets(self.session, query="Luna")[0]["id"]
        task = self.store.tasks(self.session, luna)[0]["id"]
        self.store.register("Аружан", "a@example.test", "another-pass")
        other = self.store.login("a@example.test", "another-pass")
        self.assertEqual([], self.store.list_pets(other))
        self.assertEqual([], self.store.history(other))
        for action in [
            lambda: self.store.delete_pet(other, luna),
            lambda: self.store.save_pet(other, {"name": "overwrite"}, luna),
            lambda: self.store.get_pet(other, luna),
            lambda: self.store.tasks(other, luna),
            lambda: self.store.complete_task(other, task),
            lambda: self.store.schedule_task(other, luna, dict(title="X", task_type="walk", scheduled_at="2026-10-30T09:00")),
        ]:
            with self.assertRaises(ValueError):
                action()
        self.assertNotIn("Luna", self.store.export_report(other).decode("utf-8-sig"))

    def test_task_completion_statistics_and_csv(self):
        self.store.seed_demo(self.session)
        day = "2026-10-29"
        stats = self.store.stats(self.session, day)
        self.assertEqual((10, 3, 1, 7), (stats["pet_count"], stats["task_count"], stats["done_count"], len(stats["weekly"])))
        luna = self.store.list_pets(self.session, query="Luna")[0]["id"]
        task = self.store.schedule_task(self.session, luna, {
            "task_type": "play", "title": "=formula", "scheduled_at": day + " 16:00"
        })
        self.store.complete_task(self.session, task)
        self.store.complete_task(self.session, task)
        self.assertEqual(1, sum(e["action"] == "Күтім орындалды" for e in self.store.history(self.session)))
        stats = self.store.stats(self.session, day)
        self.assertEqual((4, 2), (stats["task_count"], stats["done_count"]))
        data = self.store.export_report(self.session)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertIn(["Luna", "play", "'=formula", day + "T16:00", "Орындалды"], rows)
        limited = self.store.export_report(self.session, "2026-11-01", "2026-11-08")
        self.assertEqual(3, len(limited.decode("utf-8-sig").splitlines()))
        self.assertEqual(2, len(self.store.history(self.session, "=formula")))

    def test_bad_pet_does_not_overwrite_valid_data(self):
        self.store.seed_demo(self.session)
        luna = self.store.list_pets(self.session, query="Luna")[0]
        for field, value in [("weight_kg", float("nan")), ("weight_kg", -1), ("name", ""), ("birth_date", "2999-01-01")]:
            with self.assertRaises(ValueError):
                self.store.save_pet(self.session, {field: value}, luna["id"])
        self.assertEqual(luna, self.store.get_pet(self.session, luna["id"]))

    def test_reset_is_single_use_and_revokes_sessions(self):
        codes = []
        self.store.request_reset("balnur@example.test", lambda email, code: codes.append(code))
        self.store.request_reset("balnur@example.test", lambda email, code: codes.append(code))
        self.assertEqual(1, len(codes))
        self.store.reset_password("balnur@example.test", codes[0], "changed-password")
        for action in [
            lambda: self.store.profile(self.session),
            lambda: self.store.reset_password("balnur@example.test", codes[0], "changed-again"),
            lambda: self.store.login("balnur@example.test", "student-pass"),
        ]:
            with self.assertRaises(ValueError):
                action()
        fresh = self.store.login("balnur@example.test", "changed-password")
        self.assertEqual("Балнұр", self.store.profile(fresh)["name"])
        self.store.logout(fresh)
        with self.assertRaises(ValueError):
            self.store.owner(fresh)

    def test_reset_expiry_and_send_failure(self):
        codes = []
        with patch("petcare.db.auth.time.time", return_value=1000):
            self.store.request_reset("balnur@example.test", lambda email, code: codes.append(code))
        with patch("petcare.db.auth.time.time", return_value=1601), self.assertRaises(ValueError):
            self.store.reset_password("balnur@example.test", codes[0], "new-password")

        def fail(email, code):
            codes.append(code)
            raise RuntimeError("SMTP unavailable")
        with self.assertRaises(RuntimeError):
            self.store.request_reset("balnur@example.test", fail)
        with self.assertRaises(ValueError):
            self.store.reset_password("balnur@example.test", codes[-1], "new-password")

    def test_change_password_conflicting_email_and_attempt_limit(self):
        codes = []
        self.store.register("Екінші", "second@example.test", "student-pass")
        with self.assertRaises(ValueError):
            self.store.update_profile(self.session, "Жаңа", "second@example.test")
        self.assertEqual("Балнұр", self.store.profile(self.session)["name"])
        second_session = self.store.login("balnur@example.test", "student-pass")
        self.store.change_password(self.session, "student-pass", "changed-password")
        with self.assertRaises(ValueError):
            self.store.owner(second_session)
        self.store.request_reset("balnur@example.test", lambda email, code: codes.append(code))
        for index in range(5):
            with self.assertRaises(ValueError):
                self.store.reset_password("balnur@example.test", "invalid", "other-password")
        with self.assertRaises(ValueError):
            self.store.reset_password("balnur@example.test", codes[0], "other-password")

