import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from decide import cli
from decide.cache import Cache
from decide.client import DecisionError, Response
from decide.config import BACKENDS
from decide.engine import Document, Engine, chunk
from decide.files import discover
from decide.questions import combine, noul


class FakeClient:
    """Answers P(yes)=0.9 for any question whose keyword appears in the chunk."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def ask(self, state, questions):
        self.calls.append(state)
        if self.fail_on and self.fail_on in state:
            raise DecisionError("boom")
        answers = {name: {"type": "noul", "noul": 0.9 if q["instructions"].split()[-1] in state else 0.05}
                   for name, q in questions.items()}
        return Response(answers, len(state) // 4, 0.01)


class ConfigTest(unittest.TestCase):
    def test_key_file_location(self):
        from decide import config
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            os.environ["XDG_CONFIG_HOME"] = tmp
            self.assertEqual(config.env_file(), Path(tmp) / "decide" / "env")
            (Path(tmp) / "decide").mkdir()
            (Path(tmp) / "decide" / "env").write_text("# keys\nexport TYPESAFE_API_KEY='abc'\n")
            self.assertEqual(config.get_backend("jev").api_key, "abc")
            os.environ["DECIDE_ENV_FILE"] = "~/elsewhere"
            self.assertEqual(config.env_file(), Path.home() / "elsewhere")

    def test_environment_wins_and_missing_key_is_explained(self):
        from decide import config
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            os.environ["DECIDE_ENV_FILE"] = str(Path(tmp) / "env")
            with self.assertRaises(SystemExit) as e:
                config.get_backend("jev")
            self.assertIn("TYPESAFE_API_KEY", str(e.exception))
            (Path(tmp) / "env").write_text("TYPESAFE_API_KEY=from-file\n")
            os.environ["TYPESAFE_API_KEY"] = "from-env"
            self.assertEqual(config.get_backend("jev").api_key, "from-env")
            self.assertEqual(config.get_backend("ollama").api_key, None, "ollama needs no key")


class ChunkTest(unittest.TestCase):
    def test_respects_limit_and_preserves_text(self):
        text = "".join(f"line {i}\n" for i in range(1000))
        parts = chunk(text, 500)
        self.assertTrue(all(len(p) <= 500 for p in parts))
        self.assertEqual("".join(parts), text)

    def test_hard_splits_long_line(self):
        parts = chunk("x" * 1200, 500)
        self.assertEqual([len(p) for p in parts], [500, 500, 200])

    def test_empty_text_is_one_chunk(self):
        self.assertEqual(chunk("", 100), [""])


class CombineTest(unittest.TestCase):
    def test_noul_takes_max(self):
        self.assertEqual(combine([{"type": "noul", "noul": 0.2}, {"type": "noul", "noul": 0.7}])["noul"], 0.7)

    def test_choice_takes_max_per_option(self):
        a = {"type": "choice", "choice": "ok", "probabilities": {"ok": 0.8, "block": 0.2}}
        b = {"type": "choice", "choice": "block", "probabilities": {"ok": 0.1, "block": 0.9}}
        self.assertEqual(combine([a, b])["choice"], "block")


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.backend = BACKENDS["jev"].__class__(**{**BACKENDS["jev"].__dict__, "max_chunk_chars": 1000})

    def test_yes_in_any_chunk_wins(self):
        text = "filler\n" * 400 + "needle\n" + "filler\n" * 400
        engine = Engine(self.backend, client=FakeClient())
        [result] = engine.run([Document("f.py", text)], {"q": noul("contains needle")})
        self.assertGreater(result.chunks, 2)
        self.assertEqual(result.answers["q"]["noul"], 0.9)

    def test_cache_avoids_second_call(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            engine = Engine(self.backend, Cache(Path(d)), client)
            docs, qs = [Document("f.py", "needle")], {"q": noul("contains needle")}
            engine.run(docs, qs)
            [again] = engine.run(docs, qs)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual((again.cached_chunks, again.input_tokens), (1, 0))

    def test_error_is_reported_per_document(self):
        engine = Engine(self.backend, client=FakeClient(fail_on="bad"))
        good, bad = engine.run([Document("a", "fine"), Document("b", "bad")], {"q": noul("x needle")})
        self.assertIsNone(good.error)
        self.assertEqual(bad.error, "boom")


class DiscoverTest(unittest.TestCase):
    def test_skips_sensitive_binary_and_empty(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("print(1)")
            (root / ".env").write_text("KEY=1")
            (root / "server.pem").write_text("-----BEGIN")
            (root / "blob.bin").write_bytes(b"\0\1\2")
            (root / "empty.txt").write_text("")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "x.js").write_text("x")
            files, skipped = discover([d])
            self.assertEqual([f.name for f in files], ["app.py"])
            reasons = {p.name: r for p, r in skipped}
            self.assertTrue(reasons[".env"].startswith("sensitive"))
            self.assertTrue(reasons["server.pem"].startswith("sensitive"))

    def test_explicit_sensitive_file_still_refused(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("KEY=1")
            files, skipped = discover([str(env)])
            self.assertEqual(files, [])


class TriageCliTest(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--no-cache", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_prints_only_matches_sorted(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}), \
                mock.patch("decide.engine.Client", lambda backend: FakeClient()):
            (Path(d) / "a.py").write_text("nothing here")
            (Path(d) / "b.py").write_text("the needle is here")
            code, out, err = self.run_cli("triage", "-q", "mentions needle", d)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), [f"0.90  {Path(d) / 'b.py'}"])
        self.assertIn("1/2 files matched", err)

    def test_json_and_match_all(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}), \
                mock.patch("decide.engine.Client", lambda backend: FakeClient()):
            (Path(d) / "a.py").write_text("alpha only")
            (Path(d) / "b.py").write_text("alpha and beta")
            code, out, _ = self.run_cli("triage", "-q", "has alpha", "-q", "has beta", "--match", "all", "--json", d)
        rows = {Path(r["path"]).name: r["match"] for r in json.loads(out)["files"]}
        self.assertEqual(rows, {"a.py": False, "b.py": True})

    def test_max_files_guard(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}):
            for i in range(3):
                (Path(d) / f"{i}.py").write_text("x")
            code, _, err = self.run_cli("triage", "-q", "x", "--max-files", "2", d)
        self.assertEqual(code, 2)
        self.assertIn("exceeds --max-files", err)


if __name__ == "__main__":
    unittest.main()
