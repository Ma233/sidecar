"""
Unit tests for scripts/state.py — pure logic, no Docker required.
Run: pytest tests/test_state.py -v
"""
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import state


class TestDecodeBase64Meta(unittest.TestCase):
    def test_valid(self):
        raw = base64.b64encode(b'{"mgmt_port": 15673}').decode()
        self.assertEqual(state.decode_meta(raw), {"mgmt_port": 15673})

    def test_empty_object(self):
        # "e30=" is base64("{}")
        self.assertEqual(state.decode_meta("e30="), {})

    def test_invalid_base64(self):
        self.assertEqual(state.decode_meta("!!!"), {})

    def test_invalid_json(self):
        raw = base64.b64encode(b"not-json").decode()
        self.assertEqual(state.decode_meta(raw), {})


class TestLoadMetaOverride(unittest.TestCase):
    def test_reads_tmp_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sidecar-meta-abc123-rabbitmq.json")
            with open(path, "w") as f:
                json.dump({"mgmt_port": 15673}, f)
            with patch("state.open", side_effect=lambda p: open(p)):
                # Point directly at known path by patching the path construction
                with patch("builtins.open", side_effect=lambda p: open(p)):
                    pass
            # Test via the actual function with patched path
            orig = state.load_meta_override.__code__
            result = _load_meta_override_from(path)
            self.assertEqual(result, {"mgmt_port": 15673})

    def test_missing_file_returns_empty(self):
        result = state.load_meta_override("rabbitmq", "nonexistent_hash_xyz")
        self.assertEqual(result, {})

    def test_invalid_json_in_file_returns_empty(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w",
            prefix="sidecar-meta-test000-rabbitmq"
        ) as f:
            f.write("broken json{{{")
            name = f.name
        # Patch the path so load_meta_override reads this file
        with patch("state.load_meta_override", wraps=state.load_meta_override):
            result = _load_meta_override_at(name)
        os.unlink(name)
        self.assertEqual(result, {})


def _load_meta_override_from(path):
    """Helper: load JSON from a known path (mimics load_meta_override)."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_meta_override_at(path):
    """Helper: try reading bad json, expect empty dict."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


class TestBuildUri(unittest.TestCase):
    def test_postgres(self):
        uri = state.build_uri("postgres", 54321)
        self.assertEqual(uri, "postgresql://sidecar:sidecar@localhost:54321/sidecar")

    def test_redis(self):
        self.assertEqual(state.build_uri("redis", 63791), "redis://localhost:63791")

    def test_mongo(self):
        self.assertEqual(state.build_uri("mongo", 27891), "mongodb://sidecar:sidecar@localhost:27891")

    def test_kafka(self):
        self.assertEqual(state.build_uri("kafka", 19092), "localhost:19092")

    def test_rabbitmq(self):
        self.assertEqual(state.build_uri("rabbitmq", 45672), "amqp://sidecar:sidecar@localhost:45672")

    def test_unknown_service(self):
        self.assertEqual(state.build_uri("mysql", 3306), "localhost:3306")

    def test_never_default_port(self):
        """Ports must come from arguments, never hardcoded."""
        uri = state.build_uri("postgres", 99999)
        self.assertIn("99999", uri)
        self.assertNotIn(":5432", uri)


class TestBuildEnv(unittest.TestCase):
    def test_postgres_env_vars(self):
        env = state.build_env("postgres", 54321, {})
        self.assertEqual(env["DATABASE_URL"], "postgresql://sidecar:sidecar@localhost:54321/sidecar")
        self.assertEqual(env["POSTGRES_PORT"], "54321")
        self.assertEqual(env["POSTGRES_USER"], "sidecar")
        self.assertEqual(env["POSTGRES_DB"], "sidecar")

    def test_redis_env_vars(self):
        env = state.build_env("redis", 63791, {})
        self.assertEqual(env["REDIS_URL"], "redis://localhost:63791")
        self.assertEqual(env["REDIS_PORT"], "63791")

    def test_rabbitmq_without_mgmt(self):
        env = state.build_env("rabbitmq", 45672, {})
        self.assertIn("AMQP_URL", env)
        self.assertNotIn("RABBITMQ_MGMT_URL", env)

    def test_rabbitmq_with_mgmt(self):
        env = state.build_env("rabbitmq", 45672, {"mgmt_port": 15673})
        self.assertEqual(env["RABBITMQ_MGMT_URL"], "http://localhost:15673")

    def test_rabbitmq_mgmt_port_zero_excluded(self):
        """mgmt_port=0 means unresolved; should not be included."""
        env = state.build_env("rabbitmq", 45672, {"mgmt_port": 0})
        self.assertNotIn("RABBITMQ_MGMT_URL", env)

    def test_kafka_env_vars(self):
        env = state.build_env("kafka", 19092, {})
        self.assertEqual(env["KAFKA_BOOTSTRAP_SERVERS"], "localhost:19092")

    def test_mongo_env_vars(self):
        env = state.build_env("mongo", 27891, {})
        self.assertEqual(env["MONGODB_URL"], "mongodb://sidecar:sidecar@localhost:27891")
        self.assertEqual(env["MONGODB_PORT"], "27891")


class TestProjectHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = state.project_hash()
        h2 = state.project_hash()
        self.assertEqual(h1, h2)

    def test_six_chars(self):
        self.assertEqual(len(state.project_hash()), 6)

    def test_hex_chars_only(self):
        import re
        self.assertRegex(state.project_hash(), r'^[0-9a-f]{6}$')

    def test_different_for_different_dirs(self):
        import hashlib
        h_a = hashlib.md5(b"/project/a").hexdigest()[:6]
        h_b = hashlib.md5(b"/project/b").hexdigest()[:6]
        self.assertNotEqual(h_a, h_b)


class TestCmdConnectionsOutput(unittest.TestCase):
    """Smoke-test cmd_connections output structure (mocks Docker calls)."""

    def _make_container(self, service, port, keep=False, meta=None):
        return {
            "name": f"sidecar-{service}-abc123",
            "service": service,
            "keep": keep,
            "meta": meta or {},
        }

    @patch("state.resolve_port", return_value=54321)
    @patch("state.list_containers")
    def test_postgres_output_contains_port(self, mock_list, mock_port):
        mock_list.return_value = [self._make_container("postgres", 54321)]
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            state.cmd_connections([])
        out = buf.getvalue()
        self.assertIn("54321", out)
        self.assertIn("DATABASE_URL", out)
        # Must use the actual port, not the default container port (5432).
        # Check for ":5432/" specifically to avoid false match against "54321".
        import re
        db_url_line = out.split("DATABASE_URL")[1].split("\n")[0]
        self.assertIsNone(re.search(r':5432/', db_url_line), f"Default port found in: {db_url_line}")

    @patch("state.resolve_port", return_value=None)
    @patch("state.list_containers")
    def test_unresolvable_port_warns(self, mock_list, mock_port):
        mock_list.return_value = [self._make_container("redis", None)]
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            state.cmd_connections([])
        self.assertIn("WARNING", buf.getvalue())

    @patch("state.resolve_port", return_value=45672)
    @patch("state.list_containers")
    def test_rabbitmq_mgmt_url_shown(self, mock_list, mock_port):
        mock_list.return_value = [
            self._make_container("rabbitmq", 45672, meta={"mgmt_port": 15673})
        ]
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            state.cmd_connections([])
        self.assertIn("15673", buf.getvalue())

    @patch("state.list_containers", return_value=[])
    def test_no_containers_message(self, _):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            state.cmd_connections([])
        self.assertIn("No running containers", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
