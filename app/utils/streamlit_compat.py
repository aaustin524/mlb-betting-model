"""Helpers for modules shared between Streamlit and non-Streamlit entrypoints.

When these modules are imported by Reflex or scripts, we do not want Streamlit
cache decorators to emit warnings about a missing runtime. In a real Streamlit
session we still want normal `st.cache_data` behavior.
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st


def cache_data_if_runtime(*args: Any, **kwargs: Any) -> Callable:
    """Use `st.cache_data` only when running inside an active Streamlit runtime."""
    try:
        from streamlit.runtime import exists

        if exists():
            return st.cache_data(*args, **kwargs)
    except Exception:
        pass

    def decorator(func: Callable) -> Callable:
        return func

    return decorator
