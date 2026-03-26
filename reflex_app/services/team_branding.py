"""UI branding helpers for team colors and local logo assets.

This stays inside the Reflex service layer because it is presentation-only.
It does not affect probabilities, simulations, or any model outputs.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import quote

from project_config import BASE_DIR

TEAM_BRANDING = {
    "Arizona Diamondbacks": {"abbr": "ARI", "primary": "#A71930", "secondary": "#E3D4AD"},
    "Atlanta Braves": {"abbr": "ATL", "primary": "#CE1141", "secondary": "#13274F"},
    "Baltimore Orioles": {"abbr": "BAL", "primary": "#DF4601", "secondary": "#000000"},
    "Boston Red Sox": {"abbr": "BOS", "primary": "#BD3039", "secondary": "#0C2340"},
    "Chicago Cubs": {"abbr": "CHC", "primary": "#0E3386", "secondary": "#CC3433"},
    "Chicago White Sox": {"abbr": "CWS", "primary": "#111111", "secondary": "#C4CED4"},
    "Cincinnati Reds": {"abbr": "CIN", "primary": "#C6011F", "secondary": "#000000"},
    "Cleveland Guardians": {"abbr": "CLE", "primary": "#0C2340", "secondary": "#E31937"},
    "Colorado Rockies": {"abbr": "COL", "primary": "#33006F", "secondary": "#C4CED4"},
    "Detroit Tigers": {"abbr": "DET", "primary": "#0C2340", "secondary": "#FA4616"},
    "Houston Astros": {"abbr": "HOU", "primary": "#002D62", "secondary": "#EB6E1F"},
    "Kansas City Royals": {"abbr": "KC", "primary": "#004687", "secondary": "#BD9B60"},
    "Los Angeles Angels": {"abbr": "LAA", "primary": "#BA0021", "secondary": "#862633"},
    "Los Angeles Dodgers": {"abbr": "LAD", "primary": "#005A9C", "secondary": "#EF3E42"},
    "Miami Marlins": {"abbr": "MIA", "primary": "#00A3E0", "secondary": "#EF3340"},
    "Milwaukee Brewers": {"abbr": "MIL", "primary": "#12284B", "secondary": "#FFC52F"},
    "Minnesota Twins": {"abbr": "MIN", "primary": "#002B5C", "secondary": "#D31145"},
    "New York Mets": {"abbr": "NYM", "primary": "#002D72", "secondary": "#FF5910"},
    "New York Yankees": {"abbr": "NYY", "primary": "#132448", "secondary": "#C4CED3"},
    "Oakland Athletics": {"abbr": "OAK", "primary": "#003831", "secondary": "#EFB21E"},
    "Philadelphia Phillies": {"abbr": "PHI", "primary": "#E81828", "secondary": "#002D72"},
    "Pittsburgh Pirates": {"abbr": "PIT", "primary": "#27251F", "secondary": "#FDB827"},
    "San Diego Padres": {"abbr": "SD", "primary": "#2F241D", "secondary": "#FFC425"},
    "San Francisco Giants": {"abbr": "SF", "primary": "#FD5A1E", "secondary": "#27251F"},
    "Seattle Mariners": {"abbr": "SEA", "primary": "#0C2C56", "secondary": "#005C5C"},
    "St. Louis Cardinals": {"abbr": "STL", "primary": "#C41E3A", "secondary": "#0C2340"},
    "Tampa Bay Rays": {"abbr": "TB", "primary": "#092C5C", "secondary": "#8FBCE6"},
    "Texas Rangers": {"abbr": "TEX", "primary": "#003278", "secondary": "#C0111F"},
    "Toronto Blue Jays": {"abbr": "TOR", "primary": "#134A8E", "secondary": "#1D2D5C"},
    "Washington Nationals": {"abbr": "WSH", "primary": "#AB0003", "secondary": "#14225A"},
}

TEAM_LOGO_SLUGS = {
    "Arizona Diamondbacks": "ari",
    "Atlanta Braves": "atl",
    "Baltimore Orioles": "bal",
    "Boston Red Sox": "bos",
    "Chicago Cubs": "chc",
    "Chicago White Sox": "chw",
    "Cincinnati Reds": "cin",
    "Cleveland Guardians": "cle",
    "Colorado Rockies": "col",
    "Detroit Tigers": "det",
    "Houston Astros": "hou",
    "Kansas City Royals": "kc",
    "Los Angeles Angels": "laa",
    "Los Angeles Dodgers": "lad",
    "Miami Marlins": "mia",
    "Milwaukee Brewers": "mil",
    "Minnesota Twins": "min",
    "New York Mets": "nym",
    "New York Yankees": "nyy",
    "Oakland Athletics": "oak",
    "Philadelphia Phillies": "phi",
    "Pittsburgh Pirates": "pit",
    "San Diego Padres": "sd",
    "San Francisco Giants": "sf",
    "Seattle Mariners": "sea",
    "St. Louis Cardinals": "stl",
    "Tampa Bay Rays": "tb",
    "Texas Rangers": "tex",
    "Toronto Blue Jays": "tor",
    "Washington Nationals": "wsh",
}

TEAM_LOGO_DIR = BASE_DIR / "app" / "assets" / "team_logos"


def get_team_branding(team_name: str | None) -> dict[str, str]:
    team_text = str(team_name).strip() if team_name else ""
    default = {
        "abbr": team_text[:3].upper() if team_text else "MLB",
        "primary": "#2563EB",
        "secondary": "#1E293B",
    }
    return TEAM_BRANDING.get(team_text, default)


def _build_team_logo_data_uri(team_name: str | None) -> str:
    branding = get_team_branding(team_name)
    abbr = branding["abbr"]
    primary = branding["primary"]
    secondary = branding["secondary"]
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{primary}" />
          <stop offset="100%" stop-color="{secondary}" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="64" height="64" rx="18" fill="url(#g)" />
      <rect x="7" y="7" width="58" height="58" rx="15" fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="1.5" />
      <circle cx="36" cy="36" r="24" fill="rgba(6,12,22,0.18)" />
      <text x="36" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="800" letter-spacing="1.5" fill="#F8FAFC">{abbr}</text>
    </svg>
    """.strip()
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def get_team_logo_src(team_name: str | None) -> str:
    """Return a data URI for a local logo asset when available."""
    team_text = str(team_name).strip() if team_name else ""
    slug = TEAM_LOGO_SLUGS.get(team_text)
    if slug:
        for ext in ("svg", "png", "webp", "jpg", "jpeg"):
            candidate = TEAM_LOGO_DIR / f"{slug}.{ext}"
            if candidate.exists():
                mime_type = mimetypes.guess_type(candidate.name)[0] or "image/png"
                encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
                return f"data:{mime_type};base64,{encoded}"
    return _build_team_logo_data_uri(team_text)
