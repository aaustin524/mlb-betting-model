"""Shared service layer for app-facing data shaping.

These services sit between core model code and UI frameworks.
They return plain Python or pandas structures so Streamlit and Reflex can
share the same underlying board-building logic.
"""

