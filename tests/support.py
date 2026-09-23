"""Shared helpers: import a skill script by name, and run one as a CLI offline."""
import importlib.util
import os
import subprocess
import sys

import tests  # noqa: F401  (installs the socket guard)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
SCRIPTS = {
    "hookscore": "ig-reel", "beats": "ig-reel", "formula": "ig-reel", "fit": "ig-reel",
    "caption": "ig-caption", "detect": "ig-human", "humanize": "ig-human",
    "jev": "ig-human", "proofcheck": "ig-human", "swipe": "ig-viral",
}


def load(name):
    """Import skills/<folder>/<name>.py once, with its folder on sys.path."""
    if name in sys.modules:
        return sys.modules[name]
    folder = os.path.join(SKILLS, SCRIPTS[name])
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name, os.path.join(folder, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def clean_env(extra=None):
    """The caller's environment without the API key, and with Jev switched off."""
    env = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "IG_JEV_DEBUG")}
    env["IG_JEV"] = "off"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra or {})
    return env


def run_cli(script_rel, args, stdin=None, env_extra=None):
    return subprocess.run([sys.executable, os.path.join(SKILLS, script_rel)] + list(args),
                          input=stdin, capture_output=True, text=True,
                          env=clean_env(env_extra), cwd=ROOT)


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()
