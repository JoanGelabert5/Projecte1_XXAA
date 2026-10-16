import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg
import redis

from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        db_patch = patch("app.psycopg.connect")
        redis_patch = patch("app.redis.Redis")
        self.connect = db_patch.start()
        self.redis_factory = redis_patch.start()
        self.addCleanup(db_patch.stop)
        self.addCleanup(redis_patch.stop)
        self.connection = self.connect.return_value.__enter__.return_value
        self.cache = self.redis_factory.return_value
        self.cache.get.return_value = None
        self.cache.ping.return_value = True
        self.note = {"id": 1, "content": "Una nota", "created_at": datetime.now(timezone.utc)}
        self.connection.execute.return_value.fetchall.return_value = [self.note]
        self.connection.execute.return_value.fetchone.return_value = self.note

    def client(self, production=False):
        return create_app({"TESTING": True, "CACHE_ENABLED": production}).test_client()

    def test_dev_status_does_not_need_redis(self):
        response = self.client().get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["services"]["cache"], "not_configured")
        self.redis_factory.assert_not_called()

    def test_db_failure_and_recovery_are_rechecked(self):
        client = self.client()
        self.connect.side_effect = psycopg.OperationalError("private connection details")
        response = client.get("/status")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.get_data(as_text=True))
        self.connect.side_effect = None
        self.assertEqual(client.get("/status").status_code, 200)

    def test_redis_failure_marks_production_unhealthy(self):
        self.cache.ping.side_effect = redis.ConnectionError()
        response = self.client(True).get("/status")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["services"]["database"], "connected")
        self.assertEqual(response.json["services"]["cache"], "disconnected")

    def test_cache_hit_avoids_database(self):
        self.cache.get.return_value = json.dumps([{"id": 1, "content": "Guardada"}])
        response = self.client(True).get("/api/notes")
        self.assertEqual(response.json["source"], "redis")
        self.connect.assert_not_called()

    def test_cache_miss_fills_cache_with_ttl(self):
        response = self.client(True).get("/api/notes")
        self.assertEqual(response.json["source"], "postgresql")
        self.assertEqual(response.json["cache"], "miss")
        self.assertEqual(self.cache.setex.call_args.args[:2], ("notes:list", 30))

    def test_ascii_output_for_database_and_existing_cache_preserves_originals(self):
        original = "Caché, producción, mañana, il·lusió 😀"
        expected = "Cache, produccion, manana, illusio "
        self.note["content"] = original
        client = self.client(True)
        response = client.get("/api/notes")
        self.assertEqual(response.json["notes"][0]["content"], expected)
        cached = self.cache.setex.call_args.args[2]
        self.assertEqual(json.loads(cached)[0]["content"], original)
        self.cache.get.return_value = cached
        response = client.get("/api/notes")
        self.assertEqual(response.json["cache"], "hit")
        self.assertEqual(response.json["notes"][0]["content"], expected)
        self.assertNotIn(b"\\u", response.data)
        response = client.post("/api/notes", json={"content": original})
        self.assertEqual(response.json["note"]["content"], expected)
        self.assertEqual(self.connection.execute.call_args.args[1], (original,))

    def test_cache_failure_falls_back_to_database(self):
        self.cache.get.side_effect = redis.ConnectionError()
        response = self.client(True).get("/api/notes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["cache"], "unavailable")
        self.assertEqual(response.json["source"], "postgresql")

    def test_failed_cache_write_still_returns_notes(self):
        self.cache.setex.side_effect = redis.ConnectionError()
        response = self.client(True).get("/api/notes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["cache"], "unavailable")

    def test_database_failure_returns_503_without_cache(self):
        self.connect.side_effect = psycopg.OperationalError()
        self.assertEqual(self.client().get("/api/notes").status_code, 503)

    def test_insert_is_parameterized_and_invalidates_cache_after_commit(self):
        content = "Robert'); DROP TABLE notes; --"
        self.note["content"] = content
        def check_commit(*args):
            self.connect.return_value.__exit__.assert_called_once()
        self.cache.delete.side_effect = check_commit
        response = self.client(True).post("/api/notes", json={"content": content})
        self.assertEqual(response.status_code, 201)
        sql, params = self.connection.execute.call_args.args
        self.assertNotIn(content, sql)
        self.assertEqual(params, (content,))
        self.cache.delete.assert_called_once_with("notes:list")

    def test_failed_insert_does_not_invalidate_cache(self):
        self.connect.side_effect = psycopg.OperationalError()
        response = self.client(True).post("/api/notes", json={"content": "Nota"})
        self.assertEqual(response.status_code, 503)
        self.cache.delete.assert_not_called()

    def test_invalidation_failure_keeps_successful_insert(self):
        self.cache.delete.side_effect = redis.ConnectionError()
        response = self.client(True).post("/api/notes", json={"content": "Nota"})
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json["warning"])

    def test_reject_invalid_content_before_connecting(self):
        client = self.client()
        for payload in ({}, [], {"content": 4}, {"content": " "}, {"content": "x" * 501}):
            with self.subTest(payload=payload):
                self.assertEqual(client.post("/api/notes", json=payload).status_code, 400)
        self.connect.assert_not_called()

    def test_index_still_loads_when_services_fail(self):
        self.connect.side_effect = psycopg.OperationalError()
        response = self.client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PostgreSQL", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
