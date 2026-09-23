"""Test package. Every test runs offline: a real socket connect raises, the
API key is removed from the environment and Jev starts switched off. A test
that exercises the Jev path sets its own fake key and transport."""
import os
import socket

os.environ.pop("TYPESAFE_API_KEY", None)
os.environ.pop("IG_JEV_DEBUG", None)
os.environ["IG_JEV"] = "off"


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("tests must not touch the network")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
