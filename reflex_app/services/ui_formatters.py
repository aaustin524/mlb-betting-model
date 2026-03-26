"""UI-only formatting helpers for Reflex presentation layers.

These helpers do not change model outputs. They only reshape values for display.
"""

from __future__ import annotations

SHORT_TEAM_NAMES = {
    "Arizona Diamondbacks": "Diamondbacks",
    "Atlanta Braves": "Braves",
    "Baltimore Orioles": "Orioles",
    "Boston Red Sox": "Red Sox",
    "Chicago Cubs": "Cubs",
    "Chicago White Sox": "White Sox",
    "Cincinnati Reds": "Reds",
    "Cleveland Guardians": "Guardians",
    "Colorado Rockies": "Rockies",
    "Detroit Tigers": "Tigers",
    "Houston Astros": "Astros",
    "Kansas City Royals": "Royals",
    "Los Angeles Angels": "Angels",
    "Los Angeles Dodgers": "Dodgers",
    "Miami Marlins": "Marlins",
    "Milwaukee Brewers": "Brewers",
    "Minnesota Twins": "Twins",
    "New York Mets": "Mets",
    "New York Yankees": "Yankees",
    "Athletics": "Athletics",
    "Philadelphia Phillies": "Phillies",
    "Pittsburgh Pirates": "Pirates",
    "San Diego Padres": "Padres",
    "San Francisco Giants": "Giants",
    "Seattle Mariners": "Mariners",
    "St. Louis Cardinals": "Cardinals",
    "Tampa Bay Rays": "Rays",
    "Texas Rangers": "Rangers",
    "Toronto Blue Jays": "Blue Jays",
    "Washington Nationals": "Nationals",
}


def short_team_name(team: str) -> str:
    """Return a compact MLB team name for tight UI rows."""
    return SHORT_TEAM_NAMES.get(team, team)


def format_matchup_label(away_team: str, home_team: str) -> str:
    """Build a compact matchup label for dashboard/card headers."""
    return f"{short_team_name(away_team)} @ {short_team_name(home_team)}"


def format_signal_label(flag: str) -> str:
    """Map board flags into compact display labels."""
    if flag == "Strong Bet":
        return "Strong"
    if flag == "Lean":
        return "Lean"
    return "Pass"


def probability_to_american_odds(probability: float) -> int | None:
    """Convert a decimal win probability into fair American odds."""
    if probability <= 0 or probability >= 1:
        return None
    if probability >= 0.5:
        return int(round(-((probability / (1 - probability)) * 100)))
    return int(round(((1 - probability) / probability) * 100))


def format_american_odds(probability: float) -> str:
    """Return fair American odds in standard signed format."""
    odds = probability_to_american_odds(probability)
    if odds is None:
        return ""
    if odds > 0:
        return f"+{odds}"
    return str(odds)


def coerce_probability(probability_value: str | float | int | None) -> float | None:
    """Parse probability inputs from percent or decimal strings into decimal form."""
    if probability_value in (None, ""):
        return None
    try:
        text = str(probability_value).replace("%", "").strip()
        numeric_value = float(text)
    except (TypeError, ValueError):
        return None
    if numeric_value <= 0:
        return None
    if numeric_value >= 1:
        return numeric_value / 100
    return numeric_value


def format_team_probability_odds(team: str, probability_percent: str | float) -> str:
    """Format a team label with win probability and fair American odds."""
    team_label = short_team_name(team)
    probability = coerce_probability(probability_percent)
    if probability is None:
        return team_label
    percent_value = probability * 100
    odds_text = format_american_odds(probability)
    if not odds_text:
        return f"{team_label} {percent_value:.1f}%"
    return f"{team_label} {percent_value:.1f}% ({odds_text})"


def format_matchup_probability_line(
    away_team: str,
    away_probability: str | float,
    home_team: str,
    home_probability: str | float,
) -> str:
    """Build one compact Top Leans probability line."""
    away_text = format_team_probability_odds(away_team, away_probability)
    home_text = format_team_probability_odds(home_team, home_probability)
    if away_text and home_text:
        return f"{away_text}   |   {home_text}"
    return away_text or home_text
