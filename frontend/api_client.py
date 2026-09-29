"""Thin HTTP client for the FastAPI backend."""
from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")


class APIError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=180)


def get(path: str, **params):
    try:
        with _client() as c:
            r = c.get(path, params=params or None)
    except httpx.HTTPError as exc:
        raise APIError(f"API unreachable at {API_URL} ({exc})") from exc
    if r.status_code >= 400:
        raise APIError(f"{r.status_code}: {r.json().get('detail', r.text) if r.headers.get('content-type', '').startswith('application/json') else r.text}")
    return r.json()


def post(path: str, payload: dict):
    try:
        with _client() as c:
            r = c.post(path, json=payload)
    except httpx.HTTPError as exc:
        raise APIError(f"API unreachable at {API_URL} ({exc})") from exc
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise APIError(f"{r.status_code}: {detail}")
    return r.json()


def safe(fn, *args, **kwargs):
    """Call the API and show a readable error instead of a stack trace."""
    try:
        return fn(*args, **kwargs)
    except APIError as exc:
        st.error(str(exc))
        return None
