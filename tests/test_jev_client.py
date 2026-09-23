"""The single Jev client: parsing, retries, circuit breaker, config errors, secrets."""
import io
import json
import os
import socket
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock

from tests.support import load

jev = load("jev")
KEY = "ts_test_SECRET_1234567890"


def ok_body(answers, model="jev-1.13.0", usage=None):
    return json.dumps({"model": model, "answers": answers,
                       "usage": usage or {"input_tokens": 100, "output_tokens": 10}}).encode()


class FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(code, body=b"{}", headers=None):
    return urllib.error.HTTPError(jev.ENDPOINT, code, "err", headers or {}, io.BytesIO(body))


Q = {"a": {"type": "noul", "instructions": "Is it?"},
     "b": {"type": "choice", "instructions": "Which?", "criteria": {"x": "X", "y": "Y"}}}
A = {"a": {"type": "noul", "noul": 0.9},
     "b": {"type": "choice", "choice": "x", "probabilities": {"x": 0.8, "y": 0.2}, "confidence": 0.7}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": KEY}),
            mock.patch.object(jev, "CIRCUIT", os.path.join(self.tmp.name, ".jev-offline")),
            mock.patch.object(jev.time, "sleep"),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("IG_JEV", None)
        os.environ.pop("IG_JEV_DEBUG", None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class Parse(Base):
    def test_noul_and_choice(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))) as u:
            r = jev.ask({"s": 1}, Q)
        self.assertEqual(r.answers["a"]["noul"], 0.9)
        self.assertEqual(r.answers["b"]["choice"], "x")
        self.assertEqual(r.requests, 1)
        req = u.call_args[0][0]
        body = json.loads(req.data)
        self.assertEqual(body["model"], "jev-1.13.0")
        self.assertEqual(body["state"], {"s": 1})
        self.assertEqual(req.full_url, jev.ENDPOINT)

    def test_score(self):
        ans = {"s": {"type": "score", "score": 1.2, "legend": {"0": "a"},
                     "probabilities": {"0": 1.0}, "confidence": 0.5}}
        q = {"s": {"type": "score", "instructions": "How?", "criteria": ["a", "b"]}}
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(ans))):
            self.assertEqual(jev.ask("x", q).answers["s"]["score"], 1.2)


class Retry(Base):
    def test_429_then_200_respects_retry_after(self):
        seq = [http_error(429, headers={"retry-after": "2"}), FakeResp(ok_body(A))]
        with mock.patch.object(jev, "urlopen", side_effect=seq):
            jev.ask("s", Q)
        jev.time.sleep.assert_called_once_with(2.0)

    def test_retry_after_is_capped(self):
        seq = [http_error(429, headers={"retry-after": "60"}), FakeResp(ok_body(A))]
        with mock.patch.object(jev, "urlopen", side_effect=seq):
            jev.ask("s", Q)
        jev.time.sleep.assert_called_once_with(3.0)

    def test_529_three_times_is_rate_limited(self):
        with mock.patch.object(jev, "urlopen", side_effect=[http_error(529) for _ in range(3)]) as u:
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "rate-limited")
        self.assertEqual(u.call_count, 3)
        self.assertEqual([c.args[0] for c in jev.time.sleep.call_args_list], [0.5, 1.5])
        self.assertFalse(os.path.exists(jev.CIRCUIT))


class ConfigErrors(Base):
    def test_unknown_model_401_422_are_config_errors_without_retry(self):
        for err in [http_error(400, b'{"error":"Unknown model"}'), http_error(401), http_error(422)]:
            with mock.patch.object(jev, "urlopen", side_effect=[err]) as u, \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as err_out:
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            self.assertEqual(cm.exception.reason, "config-error")
            self.assertEqual(u.call_count, 1)
            self.assertIn("config error", err_out.getvalue())
        self.assertIn("Unknown model", jev.JevUnavailable("config-error", "HTTP 400: Unknown model").detail)

    def test_model_mismatch(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A, model="jev-1.14.0"))), \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "config-error")
        self.assertIn("model mismatch", cm.exception.detail)


class BadResponse(Base):
    def test_invalid_json(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(b"not json")):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "bad-response")

    def test_missing_answer_id(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body({"a": A["a"]}))):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "bad-response")

    def test_answer_of_the_wrong_type(self):
        wrong = {"a": A["a"], "b": {"type": "noul", "noul": 0.5}}
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(wrong))):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "bad-response")


class Offline(Base):
    def test_timeout_is_offline_and_trips_the_circuit(self):
        with mock.patch.object(jev, "urlopen", side_effect=[socket.timeout("timed out")]) as u:
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "offline")
        self.assertEqual(u.call_count, 1)
        self.assertTrue(os.path.exists(jev.CIRCUIT))
        with mock.patch.object(jev, "urlopen") as u2:
            with self.assertRaises(jev.JevUnavailable) as cm2:
                jev.ask("s", Q)
        u2.assert_not_called()
        self.assertEqual((cm2.exception.reason, cm2.exception.detail), ("offline", "cached"))

    def test_expired_circuit_is_ignored_and_success_clears_it(self):
        with open(jev.CIRCUIT, "w") as fh:
            fh.write("0")
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))):
            jev.ask("s", Q)
        self.assertFalse(os.path.exists(jev.CIRCUIT))

    def test_tls_error_detail(self):
        err = urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
        with mock.patch.object(jev, "urlopen", side_effect=[err]):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "offline")
        self.assertTrue(cm.exception.detail.startswith("tls:"), cm.exception.detail)

    def test_server_error_is_offline_without_circuit(self):
        with mock.patch.object(jev, "urlopen", side_effect=[http_error(503)]) as u:
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual((cm.exception.reason, u.call_count), ("offline", 1))
        self.assertFalse(os.path.exists(jev.CIRCUIT))


class Switches(Base):
    def test_ig_jev_off_and_missing_key_never_call_urlopen(self):
        with mock.patch.object(jev, "urlopen") as u:
            with mock.patch.dict(os.environ, {"IG_JEV": "off"}):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
                self.assertEqual(cm.exception.reason, "disabled")
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q, engine="off")
            self.assertEqual(cm.exception.reason, "disabled")
            with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
                self.assertEqual(cm.exception.reason, "no-key")
        u.assert_not_called()

    def test_mode_precedence(self):
        with mock.patch.dict(os.environ, {"IG_JEV": "false"}):
            self.assertEqual(jev.mode(), "off")
            self.assertEqual(jev.mode("jev"), "jev")
        with mock.patch.dict(os.environ, {"IG_JEV": "0"}):
            self.assertEqual(jev.mode(), "off")
        self.assertEqual(jev.mode(), "auto")
        self.assertEqual(jev.mode("off"), "off")


class SSLOrder(Base):
    def test_certifi_first_then_system_bundle(self):
        with mock.patch.object(jev.ssl, "create_default_context") as cdc:
            jev._ssl_context()
        cafile = cdc.call_args.kwargs.get("cafile")
        self.assertTrue(cafile is None or cafile.endswith(".pem"), cafile)

    def test_system_bundle_when_certifi_missing(self):
        with mock.patch.dict("sys.modules", {"certifi": None}), \
                mock.patch.object(jev.os.path, "exists", return_value=True), \
                mock.patch.object(jev.ssl, "create_default_context") as cdc:
            jev._ssl_context()
        self.assertEqual(cdc.call_args.kwargs.get("cafile"), "/etc/ssl/cert.pem")


class Secret(Base):
    def test_key_never_leaks(self):
        errors = [http_error(401, b'{"error":"bad key ' + KEY.encode() + b'"}'),
                  urllib.error.URLError("proxy said Bearer " + KEY)]
        for err in errors:
            with mock.patch.object(jev, "urlopen", side_effect=[err]), \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as e, \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as o:
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            blob = str(cm.exception) + cm.exception.detail + e.getvalue() + o.getvalue()
            blob += json.dumps(jev.engine_fields(error=cm.exception))
            blob += jev.engine_line(reason=cm.exception.reason, detail=cm.exception.detail)
            self.assertNotIn(KEY, blob)

    def test_debug_prints_bodies_not_headers(self):
        with mock.patch.dict(os.environ, {"IG_JEV_DEBUG": "1"}), \
                mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as e:
            jev.ask("s", Q)
        self.assertIn('"questions"', e.getvalue())
        self.assertIn('"answers"', e.getvalue())
        self.assertNotIn(KEY, e.getvalue())
        self.assertNotIn("Authorization", e.getvalue())

    def test_debug_off_prints_nothing(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as e:
            jev.ask("s", Q)
        self.assertEqual(e.getvalue(), "")


class Chunking(Base):
    QS = {f"q{i}": {"type": "noul", "instructions": "x" * 400} for i in range(10)}

    @staticmethod
    def reply(req, timeout=None, context=None):
        body = json.loads(req.data)
        return FakeResp(ok_body({k: {"type": "noul", "noul": 0.5} for k in body["questions"]}))

    def test_small_request_is_one_call(self):
        with mock.patch.object(jev, "urlopen", side_effect=self.reply) as u:
            r = jev.ask_many("s", self.QS)
        self.assertEqual((u.call_count, r.requests), (1, 1))

    def test_ask_many_splits_and_merges(self):
        with mock.patch.object(jev, "urlopen", side_effect=self.reply) as u:
            r = jev.ask_many("s", self.QS, max_tokens=400)
        self.assertGreater(u.call_count, 1)
        self.assertEqual(set(r.answers), set(self.QS))
        self.assertEqual(r.requests, u.call_count)
        self.assertEqual(r.usage["input_tokens"], 100 * u.call_count)

    def test_ask_many_all_or_nothing(self):
        calls = {"n": 0}

        def reply(req, timeout=None, context=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise http_error(401)
            return self.reply(req)
        with mock.patch.object(jev, "urlopen", side_effect=reply), \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(jev.JevUnavailable):
                jev.ask_many("s", self.QS, max_tokens=400)


class Each(Base):
    def test_order_and_all_or_nothing(self):
        def reply(req, timeout=None, context=None):
            body = json.loads(req.data)
            if body["state"] == "boom":
                raise socket.timeout("t")
            return FakeResp(ok_body({"a": {"type": "noul", "noul": 0.1 * body["state"]}}))
        q = {"a": {"type": "noul", "instructions": "?"}}
        with mock.patch.object(jev, "urlopen", side_effect=reply):
            rs = jev.ask_each([(i, q) for i in range(1, 6)])
        self.assertEqual([round(r.answers["a"]["noul"], 1) for r in rs], [0.1, 0.2, 0.3, 0.4, 0.5])
        with mock.patch.object(jev, "urlopen", side_effect=reply):
            with self.assertRaises(jev.JevUnavailable):
                jev.ask_each([(1, q), ("boom", q), (3, q)])


class Transport(Base):
    def test_set_transport_replaces_http(self):
        seen = []

        def fake(body, timeout):
            seen.append(body)
            return {"model": jev.MODEL, "answers": A, "usage": {}}
        old = jev.set_transport(fake)
        try:
            with mock.patch.object(jev, "urlopen") as u:
                jev.ask("s", Q)
            u.assert_not_called()
        finally:
            jev.set_transport(old)
        self.assertEqual(seen[0]["questions"], Q)


class ReviewRegressions(Base):
    def test_dropped_connection_and_bad_status_line_are_offline(self):
        import http.client
        for err in (http.client.IncompleteRead(b"partial"), http.client.BadStatusLine("garbage")):
            with mock.patch.object(jev, "urlopen", side_effect=[err]):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            self.assertEqual(cm.exception.reason, "offline")
            os.remove(jev.CIRCUIT)

    def test_null_usage_does_not_crash(self):
        body = json.dumps({"model": "jev-1.13.0", "answers": A,
                           "usage": {"input_tokens": None}}).encode()
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(body)):
            self.assertEqual(jev.ask("s", Q).usage, {"input_tokens": 0, "output_tokens": 0})

    def test_malformed_answers_are_bad_responses(self):
        for bad in [{"a": {"type": "noul", "noul": None}, "b": A["b"]},
                    {"a": A["a"], "b": dict(A["b"], choice="z")},
                    {"a": A["a"], "b": dict(A["b"], probabilities=None)}]:
            with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(bad))):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            self.assertEqual(cm.exception.reason, "bad-response")


class EngineLine(unittest.TestCase):
    def test_formats(self):
        r = jev.Result(answers={}, model="jev-1.13.0",
                       usage={"input_tokens": 2000, "output_tokens": 89}, elapsed_s=0.41, requests=1)
        self.assertEqual(jev.engine_line(r), "engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)")
        self.assertEqual(jev.engine_line(reason="no-key"), "engine: heuristic (no-key)")
        self.assertEqual(jev.engine_line(reason="offline", detail="cached"),
                         "engine: heuristic (offline: cached)")

    def test_fields(self):
        r = jev.Result(answers={}, usage={"input_tokens": 5, "output_tokens": 1})
        self.assertEqual(jev.engine_fields(r)["engine"], "jev")
        self.assertIsNone(jev.engine_fields(r)["engine_reason"])
        f = jev.engine_fields(error=jev.JevUnavailable("no-key"))
        self.assertEqual((f["engine"], f["engine_reason"], f["model"]), ("heuristic", "no-key", None))
        self.assertEqual(jev.engine_fields(error="client-missing")["engine_reason"], "client-missing")


if __name__ == "__main__":
    unittest.main()
