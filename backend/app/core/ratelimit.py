"""Shared per-IP rate limiter (spec §15) — used by the public chat endpoint and
the admin login (brute-force guard). Wired into app.state in main.py."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
