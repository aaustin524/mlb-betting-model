"""Reflex configuration for local runs and self-hosted deployment.

For local development the frontend talks directly to `localhost:8000`.
For hosted deployment we allow `API_URL` / `RENDER_EXTERNAL_URL` to override
the backend URL so the browser can reach the live service through a reverse
proxy.
"""

from __future__ import annotations

import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

from app.runtime_env import get_deploy_url, get_public_api_url


def _get_public_url() -> str:
    return get_public_api_url() or "http://localhost:8000"


config = rx.Config(
    app_name="reflex_app",
    api_url=_get_public_url(),
    deploy_url=get_deploy_url() or "http://localhost:3000",
    backend_host="0.0.0.0",
    backend_port=8000,
    frontend_port=3000,
    show_built_with_reflex=False,
    disable_plugins=[SitemapPlugin],
)
