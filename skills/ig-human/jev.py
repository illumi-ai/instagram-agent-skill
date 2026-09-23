#!/usr/bin/env python3
"""
jev.py - the one client every script in this pack uses to ask TypeSafe's Jev
model a question. Standard library only.

What Jev is:  a System One model. You give it a state (some text) and a set of
typed questions - Noul (probability of yes), Choice (one of a set, with the
full distribution) or Score - and it returns calibrated answers in a fraction
of a second. It does not write text, count, do arithmetic or read dates, so
the scripts keep all of that in code and only ask it for the judgments a regex
cannot make: is this sentence a claim, is this hook that formula, does this
line ask the reader to do something.

When it runs:  whenever TYPESAFE_API_KEY is set in the environment, unless
IG_JEV=off or a script is run with --engine off. Without the key, offline, or
rate limited, every script falls back to the heuristics it had before and says
so on its first line:

    engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)
    engine: heuristic (no-key)

The model is pinned. Every threshold in this pack was measured on jev-1.13.0,
so a response from any other model is treated as a configuration error, not
as an answer.

The key is read at call time and never stored, printed or written. Error text
that could contain it is scrubbed. IG_JEV_DEBUG=1 prints the request and
response bodies to stderr (never the headers); it is off by default because
the bodies contain your drafts.
"""

import http.client
import json
import os
import re
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "jev-1.13.0"           # pinned: never jev-latest
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CIRCUIT = os.path.expanduser("~/.claude/instagram/.jev-offline")
CIRCUIT_TTL = 300              # seconds to skip the network after it failed
RETRY_STATUSES = (429, 529)    # the only responses worth waiting out
BACKOFF = (0.5, 1.5)           # seconds, when the server gives no retry-after
MAX_RETRY_AFTER = 3.0          # a CLI waits this long at most
CONFIG_STATUSES = (400, 401, 403, 404, 422)
REASONS = ("no-key", "disabled", "offline", "rate-limited", "config-error",
           "bad-response", "client-missing")


class JevUnavailable(Exception):
    """Jev could not answer. `reason` is one of REASONS; `detail` is short and scrubbed."""

    def __init__(self, reason, detail=""):
        self.reason = reason
        self.detail = _scrub(str(detail))[:300]
        super().__init__(self.reason + (": " + self.detail if self.detail else ""))


@dataclass
class Result:
    answers: dict
    model: str = MODEL
    usage: dict = field(default_factory=dict)
    elapsed_s: float = 0.0
    requests: int = 1

    @property
    def tokens(self):
        return int(self.usage.get("input_tokens", 0)) + int(self.usage.get("output_tokens", 0))


def _scrub(text):
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if key and len(key) >= 8:
        text = text.replace(key, "[redacted]")
    return re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)


def mode(cli_value=None):
    """'auto' | 'jev' | 'off'. The --engine flag wins over IG_JEV, which wins over auto."""
    if cli_value in ("auto", "jev", "off"):
        return cli_value
    if os.environ.get("IG_JEV", "").strip().lower() in ("off", "0", "false"):
        return "off"
    return "auto"


def _ssl_context():
    """certifi if installed, then the system bundle, then Python's default.

    The python.org builds of Python on macOS ship without a CA bundle until
    "Install Certificates.command" is run, so the default context fails there.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


def _circuit_open():
    try:
        with open(CIRCUIT, encoding="utf-8") as fh:
            return time.time() - float(fh.read().strip() or 0) < CIRCUIT_TTL
    except (OSError, ValueError):
        return False


def _trip():
    try:
        os.makedirs(os.path.dirname(CIRCUIT), exist_ok=True)
        with open(CIRCUIT, "w", encoding="utf-8") as fh:
            fh.write(str(time.time()))
    except OSError:
        pass


def _reset():
    try:
        os.remove(CIRCUIT)
    except OSError:
        pass


def _config_error(detail):
    """A key or model problem is not an outage, so it is printed even in auto mode."""
    err = JevUnavailable("config-error", detail)
    print(f"jev: config error ({err.detail}). Check TYPESAFE_API_KEY and the pinned "
          f"model {MODEL}.", file=sys.stderr)
    return err


def _retry_wait(err, attempt):
    try:
        return min(float(err.headers.get("retry-after")), MAX_RETRY_AFTER)
    except (TypeError, ValueError, AttributeError):
        return BACKOFF[attempt]


def _http_post(body, timeout):
    """POST one request. Returns the parsed response or raises JevUnavailable."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise JevUnavailable("no-key")
    if _circuit_open():
        raise JevUnavailable("offline", "cached")
    data = json.dumps(body).encode("utf-8")
    context = _ssl_context()
    for attempt in range(len(BACKOFF) + 1):
        req = Request(ENDPOINT, data=data, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout, context=context) as resp:
                raw = resp.read()
        except HTTPError as e:
            if e.code in RETRY_STATUSES:
                if attempt < len(BACKOFF):
                    time.sleep(_retry_wait(e, attempt))
                    continue
                raise JevUnavailable("rate-limited", f"HTTP {e.code}")
            try:
                text = e.read()[:300].decode("utf-8", "replace")
            except Exception:
                text = ""
            if e.code in CONFIG_STATUSES:
                raise _config_error(f"HTTP {e.code}: {text}".strip(": "))
            raise JevUnavailable("offline", f"HTTP {e.code}")
        except URLError as e:
            _trip()
            if isinstance(e.reason, ssl.SSLError):
                raise JevUnavailable("offline", f"tls: {e.reason}")
            raise JevUnavailable("offline", str(e.reason))
        except ssl.SSLError as e:
            _trip()
            raise JevUnavailable("offline", f"tls: {e}")
        except (socket.timeout, TimeoutError, ConnectionError, OSError,
                http.client.HTTPException) as e:
            # HTTPException covers a connection dropped mid-body (IncompleteRead)
            # and a garbled status line.
            _trip()
            raise JevUnavailable("offline", str(e) or type(e).__name__)
        _reset()
        try:
            return json.loads(raw)
        except ValueError:
            raise JevUnavailable("bad-response", "response is not JSON")
    raise JevUnavailable("rate-limited", "retries exhausted")


TRANSPORT = _http_post


def set_transport(fn):
    """Swap how requests are sent (the evals replay recorded answers). Returns the old one."""
    global TRANSPORT
    old, TRANSPORT = TRANSPORT, fn
    return old


def _debug(label, payload):
    if os.environ.get("IG_JEV_DEBUG", "").strip() in ("1", "true", "yes"):
        print(f"jev debug {label}: " + _scrub(json.dumps(payload, ensure_ascii=False)),
              file=sys.stderr)


def _check(resp, questions):
    if not isinstance(resp, dict):
        raise JevUnavailable("bad-response", "response is not an object")
    if resp.get("model") != MODEL:
        raise _config_error(f"model mismatch: asked for {MODEL}, got {resp.get('model')}")
    answers = resp.get("answers")
    if not isinstance(answers, dict):
        raise JevUnavailable("bad-response", "no answers")
    for qid, q in questions.items():
        a = answers.get(qid)
        if not isinstance(a, dict):
            raise JevUnavailable("bad-response", f"no answer for {qid}")
        kind = q.get("type")
        if a.get("type") != kind or not _well_formed(kind, a, q):
            raise JevUnavailable("bad-response", f"answer for {qid} is not a well-formed {kind}")
    return answers


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _well_formed(kind, a, q):
    """The fields the scripts read are present and typed, so a malformed answer
    becomes a fallback rather than a crash."""
    if kind == "noul":
        return _number(a.get("noul"))
    if kind == "choice":
        probs = a.get("probabilities")
        return (a.get("choice") in (q.get("criteria") or {}) and isinstance(probs, dict)
                and all(_number(v) for v in probs.values()) and _number(a.get("confidence")))
    if kind == "score":
        return _number(a.get("score"))
    return False


def _usage(resp):
    usage = resp.get("usage") if isinstance(resp.get("usage"), dict) else {}
    out = {}
    for k in ("input_tokens", "output_tokens"):
        try:
            out[k] = int(usage.get(k) or 0)
        except (TypeError, ValueError):
            out[k] = 0
    return out


def ask(state, questions, *, engine=None, timeout=6.0):
    """One request: every question is answered against the same state."""
    if mode(engine) == "off":
        raise JevUnavailable("disabled")
    body = {"model": MODEL, "state": state, "questions": questions}
    _debug("request", body)
    t0 = time.monotonic()
    resp = TRANSPORT(body, timeout)
    elapsed = time.monotonic() - t0
    _debug("response", resp)
    answers = _check(resp, questions)
    return Result(answers={k: answers[k] for k in questions}, model=resp["model"],
                  usage=_usage(resp), elapsed_s=elapsed, requests=1)


def _merge(results):
    answers, usage = {}, {"input_tokens": 0, "output_tokens": 0}
    for r in results:
        answers.update(r.answers)
        for k in usage:
            usage[k] += r.usage.get(k, 0)
    return Result(answers=answers, model=MODEL, usage=usage,
                  elapsed_s=sum(r.elapsed_s for r in results),
                  requests=sum(r.requests for r in results))


def ask_many(state, questions, *, engine=None, max_tokens=48000, timeout=6.0):
    """ask(), split into several requests over the same state when it is too big.

    Tokens are estimated at four characters each. Chunks go out one after the
    other, and if any of them fails the whole call fails: a report never mixes
    Jev answers with heuristic ones.
    """
    if mode(engine) == "off":
        raise JevUnavailable("disabled")
    budget = max_tokens * 4
    base = len(json.dumps(state, ensure_ascii=False))
    if base + len(json.dumps(questions, ensure_ascii=False)) <= budget:
        return ask(state, questions, engine=engine, timeout=timeout)
    chunks, current, size = [], {}, base
    for qid, q in questions.items():
        cost = len(json.dumps({qid: q}, ensure_ascii=False))
        if current and size + cost > budget:
            chunks.append(current)
            current, size = {}, base
        current[qid] = q
        size += cost
    if current:
        chunks.append(current)
    return _merge([ask(state, c, engine=engine, timeout=timeout) for c in chunks])


def ask_each(items, *, engine=None, max_workers=4, timeout=6.0):
    """Several independent requests, in parallel, one (state, questions) pair each.

    Returns the results in order. All or nothing: if one fails, the call raises.
    """
    if mode(engine) == "off":
        raise JevUnavailable("disabled")
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(ask, s, q, engine=engine, timeout=timeout) for s, q in items]
        results, first_error = [], None
        for f in futures:
            try:
                results.append(f.result())
            except JevUnavailable as e:
                first_error = first_error or e
    if first_error:
        raise first_error
    return results


def engine_line(result=None, reason=None, detail=""):
    """The first line of every report: which engine decided, and why."""
    if result is not None:
        return (f"engine: {result.model} ({result.requests} req, {result.tokens:,} tok, "
                f"{result.elapsed_s:.1f}s)")
    return f"engine: heuristic ({reason}" + (f": {_scrub(detail)}" if detail else "") + ")"


def engine_fields(result=None, error=None):
    """The same fact for --json output."""
    if result is not None:
        return {"engine": "jev", "engine_reason": None, "engine_detail": None,
                "model": result.model, "usage": dict(result.usage), "requests": result.requests}
    if isinstance(error, JevUnavailable):
        reason, detail = error.reason, error.detail
    else:
        reason, detail = str(error or "disabled"), ""
    return {"engine": "heuristic", "engine_reason": reason, "engine_detail": detail or None,
            "model": None, "usage": None, "requests": 0}
