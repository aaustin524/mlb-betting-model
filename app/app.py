import os
import sys
import math
from datetime import datetime
from textwrap import dedent

import pandas as pd
import requests
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.schema import initialize_database
from model.game_engine import simulate_matchup
from model.lineup_strength import (
    calculate_lineup_adjustment,
    load_hitter_ratings,
    load_projected_lineups,
)
from model.schedule_loader import load_today_matchups
from model.team_loader import load_team_ratings
from model.weather_api import get_weather_for_team, load_stadium_locations
from utils.history_views import (
    ensure_history_dir,
    render_history_viewer,
    render_results_grading,
)
from utils.tracked_bets import (
    clear_tracked_bet_caches,
    normalize_team_name,
    persist_snapshot_rows_to_db,
)
from utils.performance_views import (
    render_clv_summary,
    render_performance_summary,
    render_tracked_bet_lifecycle_summary,
)
from utils.season_monitor import render_current_standings, render_season_monitor
from project_config import (
    DEFAULT_RUN_DISPERSION,
    DEFAULT_SIMS,
    LEAN_BET_EDGE_THRESHOLD,
    LEAN_BET_EV_THRESHOLD,
    LEAN_TOTAL_EV_THRESHOLD,
    STRONG_BET_EDGE_THRESHOLD,
    STRONG_BET_EV_THRESHOLD,
    STRONG_TOTAL_EDGE_THRESHOLD,
    STRONG_TOTAL_EV_THRESHOLD,
    TOTALS_LOGISTIC_K,
)

st.set_page_config(page_title="MLB Win Probability Board", layout="wide")

DATA_MODE = "local"
RUN_DISPERSION_MIN = 1.0
RUN_DISPERSION_MAX = 20.0
RUN_DISPERSION_STEP = 0.5
EDGE_PLACEHOLDER = "Pending odds"
ODDS_API_KEY_ENV_VAR = "ODDS_API_KEY"
ODDS_API_SPORT = "baseball_mlb"
ODDS_API_REGION = "us"
ODDS_API_MARKETS = "h2h,spreads,totals"
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4/sports"
HISTORY_DIR = os.getenv("MLB_MODEL_HISTORY_DIR", os.path.join("data", "history"))
GRADED_RESULTS_PATH = os.path.join(HISTORY_DIR, "graded_results.csv")
PREFERRED_SPORTSBOOKS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "caesars",
]

INPUT_COLUMNS = [
    "Away",
    "Home",
    "Away Pitcher",
    "Home Pitcher",
    "A Hand",
    "H Hand",
    "Away SP",
    "Home SP",
    "Away BP Fatigue",
    "Home BP Fatigue",
    "Away Lineup",
    "Home Lineup",
    "Manual Wx",
    "Temp",
    "Wind",
    "Away Moneyline",
    "Home Moneyline",
    "Total Line",
    "Over Price",
    "Under Price",
    "Sportsbook",
]

RESULT_COLUMNS = [
    "Away Runs",
    "Home Runs",
    "Away Win",
    "Home Win",
    "Away Implied %",
    "Home Implied %",
    "Away No-Vig %",
    "Home No-Vig %",
    "Hold %",
    "Away Consensus %",
    "Home Consensus %",
    "Consensus Hold Avg",
    "Consensus Books Used",
    "Away Fair ML",
    "Home Fair ML",
    "Away Edge %",
    "Home Edge %",
    "Away EV",
    "Home EV",
    "Projected Total",
    "Total Diff",
    "Over Edge %",
    "Under Edge %",
    "Over EV",
    "Under EV",
    "Best Total Bet",
    "Total Bet Flag",
    "Favorite",
    "Win Edge",
    "Best Bet",
    "Bet Flag",
]

MODEL_DETAIL_COLUMNS = [
    "Park",
    "Weather",
]

TABLE_COLUMNS = INPUT_COLUMNS + RESULT_COLUMNS + MODEL_DETAIL_COLUMNS


@st.cache_data(show_spinner=False)
def load_team_ratings_cached(csv_path):
    return load_team_ratings(csv_path)


team_ratings = load_team_ratings_cached("data/teams.csv")


def inject_app_styles():
    st.markdown(
        """
        <style>
        :root {
            --bg: #0E1117;
            --bg-elevated: #141821;
            --bg-card: #1C1F26;
            --bg-card-alt: #20242D;
            --border: #2C313C;
            --text: #E6E6E6;
            --text-muted: #A0A0A0;
            --positive: #2ECC71;
            --negative: #E74C3C;
            --warning: #F1C40F;
            --totals: #F39C12;
            --accent: #8B93A7;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(46, 204, 113, 0.05), transparent 22%),
                radial-gradient(circle at top right, rgba(243, 156, 18, 0.04), transparent 18%),
                linear-gradient(180deg, #0E1117 0%, #10141B 100%);
            color: var(--text);
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {
            background:
                radial-gradient(circle at top left, rgba(46, 204, 113, 0.05), transparent 22%),
                radial-gradient(circle at top right, rgba(243, 156, 18, 0.04), transparent 18%),
                linear-gradient(180deg, #0E1117 0%, #10141B 100%) !important;
            color: var(--text);
        }
        header[data-testid="stHeader"] {
            background: rgba(14, 17, 23, 0) !important;
        }
        [data-testid="stDecoration"] {
            display: none !important;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        h1, h2, h3, h4, h5, h6, p, label, span, div {
            color: inherit;
        }
        .stMarkdown, .stCaption, .stText, .stMetricLabel, .stMetricValue {
            color: var(--text);
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #1C1F26 0%, #181C23 100%);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 0.8rem 1rem;
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
        }
        div[data-testid="stMetricLabel"] {
            color: var(--text-muted);
        }
        div[data-testid="stMetricValue"] {
            color: var(--text);
        }
        .hero-panel {
            padding: 1.4rem 1.6rem;
            border-radius: 22px;
            border: 1px solid var(--border);
            background: linear-gradient(135deg, #171B22 0%, #1C1F26 100%);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
            margin-bottom: 1rem;
        }
        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.9fr) minmax(260px, 0.9fr);
            gap: 1rem;
            align-items: start;
        }
        .hero-kicker {
            color: var(--totals);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.72rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .hero-title {
            color: var(--text);
            font-size: 2.35rem;
            font-weight: 800;
            margin: 0;
        }
        .hero-subtitle {
            color: var(--text-muted);
            margin-top: 0.35rem;
            margin-bottom: 0;
            font-size: 0.98rem;
        }
        .hero-sidecar {
            border-radius: 18px;
            padding: 0.9rem 1rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid var(--border);
        }
        .hero-sidecar-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .hero-sidecar-value {
            color: var(--text);
            font-size: 1.1rem;
            font-weight: 700;
            margin-top: 0.25rem;
        }
        .hero-sidecar-copy {
            color: var(--text-muted);
            font-size: 0.86rem;
            margin-top: 0.35rem;
            line-height: 1.45;
        }
        .global-status-strip {
            margin: 0.2rem 0 1rem;
            padding: 0.85rem 0.95rem;
            border-radius: 18px;
            background: linear-gradient(180deg, #171B22 0%, #141821 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
        }
        .global-status-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) repeat(4, minmax(140px, 1fr));
            gap: 0.7rem;
            align-items: center;
        }
        .global-status-title {
            color: var(--text);
            font-size: 0.96rem;
            font-weight: 760;
        }
        .global-status-copy {
            color: var(--text-muted);
            font-size: 0.84rem;
            margin-top: 0.2rem;
            line-height: 1.4;
        }
        .global-status-chip {
            border-radius: 14px;
            padding: 0.7rem 0.8rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .global-status-label {
            color: var(--text-muted);
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .global-status-value {
            color: var(--text);
            font-size: 0.9rem;
            font-weight: 720;
            margin-top: 0.24rem;
        }
        .section-label {
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 700;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
        }
        .section-subtitle {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: -0.1rem;
            margin-bottom: 0.8rem;
        }
        .section-panel {
            margin: 0.85rem 0 1rem;
            padding: 1rem 1.05rem;
            border-radius: 20px;
            background: linear-gradient(180deg, #141821 0%, #11161D 100%);
            border: 1px solid #232833;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.20);
        }
        .sticky-summary-shell {
            position: sticky;
            top: 0.75rem;
            z-index: 10;
        }
        .board-view-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.6fr);
            gap: 0.85rem;
            align-items: stretch;
        }
        .board-view-card {
            border-radius: 18px;
            padding: 0.9rem 1rem;
            background: linear-gradient(180deg, #1B1F27 0%, #161B22 100%);
            border: 1px solid var(--border);
        }
        .freshness-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.55rem;
        }
        .freshness-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border-radius: 999px;
            padding: 0.22rem 0.65rem;
            border: 1px solid rgba(139, 147, 167, 0.22);
            background: rgba(139, 147, 167, 0.10);
            color: var(--text-muted);
            font-size: 0.76rem;
            font-weight: 600;
        }
        .board-empty-card {
            border-radius: 18px;
            padding: 1.05rem 1.1rem;
            background: linear-gradient(180deg, #1B1F27 0%, #161B22 100%);
            border: 1px solid var(--border);
        }
        .board-empty-title {
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 760;
        }
        .board-empty-copy {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: 0.35rem;
            line-height: 1.45;
        }
        .board-empty-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.7rem;
            margin-top: 0.8rem;
        }
        .board-empty-metric {
            border-radius: 14px;
            padding: 0.8rem 0.9rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .board-empty-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .board-empty-value {
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 760;
            margin-top: 0.28rem;
        }
        .control-card {
            border-radius: 18px;
            padding: 0.35rem 0.2rem 0.2rem;
            background: linear-gradient(180deg, #1B1F27 0%, #171B22 100%);
            border: 1px solid var(--border);
        }
        .board-card {
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 0.7rem 0.85rem 0.8rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
        }
        .board-card-shell {
            position: relative;
            overflow: hidden;
            border-radius: 18px;
            background: transparent;
        }
        .board-card-stripe {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 6px;
            border-radius: 18px 0 0 18px;
            background: #5F6675;
            z-index: 2;
        }
        .board-card-stripe.strong {
            background: var(--positive);
        }
        .board-card-stripe.lean {
            background: var(--warning);
        }
        .board-card-stripe.total {
            background: var(--totals);
        }
        .board-card-stripe.negative {
            background: var(--negative);
        }
        .board-status-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.28rem 0.72rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-left: auto;
        }
        .board-status-badge.top-side {
            background: rgba(46, 204, 113, 0.16);
            color: var(--positive);
            border: 1px solid rgba(46, 204, 113, 0.36);
        }
        .board-status-badge.top-total {
            background: rgba(243, 156, 18, 0.16);
            color: var(--totals);
            border: 1px solid rgba(243, 156, 18, 0.34);
        }
        .board-status-badge.lean {
            background: rgba(241, 196, 15, 0.14);
            color: var(--warning);
            border: 1px solid rgba(241, 196, 15, 0.30);
        }
        .board-status-badge.pass {
            background: rgba(139, 147, 167, 0.12);
            color: #B5BAC7;
            border: 1px solid rgba(139, 147, 167, 0.24);
        }
        .board-status-row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.2rem;
        }
        .board-card.favorite-card {
            border-color: rgba(243, 156, 18, 0.50);
        }
        .board-card.strong-side {
            border-color: rgba(46, 204, 113, 0.72);
            box-shadow: 0 0 0 1px rgba(46, 204, 113, 0.10);
        }
        .board-card.lean-side {
            border-color: rgba(241, 196, 15, 0.62);
        }
        .board-card.negative-side {
            border-color: rgba(231, 76, 60, 0.62);
        }
        .board-card.pass-side {
            border-color: #343A46;
        }
        .board-topline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.8rem;
        }
        .board-matchup {
            color: var(--text);
            font-size: 1.35rem;
            font-weight: 780;
            letter-spacing: 0.01em;
        }
        .board-subtle {
            color: var(--text-muted);
            font-size: 0.82rem;
        }
        .score-ribbon {
            margin: 0.8rem 0 0.8rem;
            padding: 0.9rem 1rem;
            border-radius: 16px;
            background: linear-gradient(135deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .score-ribbon-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .score-ribbon-value {
            color: var(--text);
            font-size: 1.08rem;
            font-weight: 760;
            margin-top: 0.28rem;
        }
        .bet-slip-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
            margin: 0.85rem 0 0.95rem;
        }
        .bet-slip-card {
            border-radius: 16px;
            padding: 0.9rem 0.95rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .bet-slip-card.side {
            background:
                radial-gradient(circle at top left, rgba(46, 204, 113, 0.08), transparent 34%),
                linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border-color: rgba(46, 204, 113, 0.26);
        }
        .bet-slip-card.total {
            background:
                radial-gradient(circle at top left, rgba(243, 156, 18, 0.08), transparent 34%),
                linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border-color: rgba(243, 156, 18, 0.24);
        }
        .bet-slip-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .bet-slip-pick {
            color: var(--text);
            font-size: 1.02rem;
            font-weight: 760;
            margin-top: 0.3rem;
        }
        .bet-slip-summary {
            color: var(--text-muted);
            font-size: 0.87rem;
            margin-top: 0.42rem;
            line-height: 1.4;
        }
        .chips-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.55rem;
        }
        .market-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 0.25rem;
        }
        .market-cell {
            padding: 0.72rem 0.82rem;
            border-radius: 14px;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .market-label {
            color: var(--text-muted);
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .market-value {
            color: var(--text);
            font-size: 0.94rem;
            font-weight: 720;
            margin-top: 0.22rem;
        }
        .favorite-badge {
            background: rgba(243, 156, 18, 0.12);
            color: var(--totals);
            border: 1px solid rgba(243, 156, 18, 0.28);
            border-radius: 999px;
            padding: 0.2rem 0.65rem;
            font-size: 0.76rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .angle-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.2rem 0.65rem;
            font-size: 0.74rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .angle-badge.favorite {
            background: rgba(243, 156, 18, 0.14);
            color: var(--totals);
            border: 1px solid rgba(243, 156, 18, 0.30);
        }
        .angle-badge.underdog {
            background: rgba(46, 204, 113, 0.14);
            color: var(--positive);
            border: 1px solid rgba(46, 204, 113, 0.30);
        }
        .angle-badge.pass {
            background: rgba(139, 147, 167, 0.12);
            color: #B5BAC7;
            border: 1px solid rgba(139, 147, 167, 0.24);
        }
        .angle-badge.over {
            background: rgba(243, 156, 18, 0.14);
            color: var(--totals);
            border: 1px solid rgba(243, 156, 18, 0.30);
        }
        .angle-badge.under {
            background: rgba(52, 152, 219, 0.14);
            color: #7FC7FF;
            border: 1px solid rgba(127, 199, 255, 0.28);
        }
        .signal-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.2rem 0.65rem;
            font-size: 0.74rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .signal-badge.strong {
            background: rgba(46, 204, 113, 0.16);
            color: var(--positive);
            border: 1px solid rgba(46, 204, 113, 0.36);
        }
        .signal-badge.lean {
            background: rgba(241, 196, 15, 0.14);
            color: var(--warning);
            border: 1px solid rgba(241, 196, 15, 0.30);
        }
        .signal-badge.pass {
            background: rgba(139, 147, 167, 0.12);
            color: #B5BAC7;
            border: 1px solid rgba(139, 147, 167, 0.24);
        }
        .signal-badge.negative {
            background: rgba(231, 76, 60, 0.16);
            color: var(--negative);
            border: 1px solid rgba(231, 76, 60, 0.32);
        }
        .signal-badge.label {
            background: rgba(160, 160, 160, 0.10);
            color: var(--text-muted);
            border: 1px solid rgba(160, 160, 160, 0.20);
        }
        .card-section-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            margin-top: 0.65rem;
            margin-bottom: 0.3rem;
        }
        .card-note {
            color: var(--text);
            font-size: 0.92rem;
            margin-top: 0.2rem;
            margin-bottom: 0.2rem;
        }
        .card-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.25rem;
            margin-bottom: 0.35rem;
        }
        .card-section-divider {
            height: 1px;
            width: 100%;
            background: linear-gradient(90deg, rgba(44, 49, 60, 0.0), rgba(44, 49, 60, 1.0), rgba(44, 49, 60, 0.0));
            margin: 0.8rem 0 0.2rem;
        }
        .probability-line {
            display: grid;
            grid-template-columns: minmax(120px, 1fr) 64px minmax(120px, 1.2fr);
            align-items: center;
            gap: 0.75rem;
            padding: 0.6rem 0.8rem;
            border-radius: 12px;
            background: #20242D;
            border: 1px solid #2A303A;
            margin-bottom: 0.45rem;
        }
        .probability-team {
            color: var(--text);
            font-size: 0.94rem;
            font-weight: 700;
        }
        .probability-value {
            color: var(--positive);
            font-size: 0.94rem;
            font-weight: 800;
            text-align: right;
        }
        .probability-bar-track {
            width: 100%;
            height: 10px;
            border-radius: 999px;
            background: #2A303A;
            overflow: hidden;
            position: relative;
        }
        .probability-bar-fill {
            height: 100%;
            border-radius: 999px;
            background: #5A5A5A;
        }
        .probability-bar-fill.favorite {
            background: var(--positive);
        }
        .probability-bar-fill.underdog {
            background: #5A5A5A;
        }
        .meta-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.65rem;
            margin-top: 0.9rem;
        }
        .meta-pill {
            border-radius: 14px;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
            padding: 0.62rem 0.8rem;
        }
        .meta-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .meta-value {
            color: var(--text);
            font-size: 0.94rem;
            font-weight: 700;
            margin-top: 0.18rem;
        }
        .toolbar-note {
            color: var(--text-muted);
            font-size: 0.9rem;
            padding-top: 0.35rem;
        }
        .top-plays-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 0.75rem;
            margin-bottom: 1rem;
        }
        .top-strip-card {
            border-radius: 16px;
            padding: 0.9rem 1rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
            min-height: 130px;
        }
        .top-strip-card.side {
            border-color: rgba(46, 204, 113, 0.42);
        }
        .top-strip-card.total {
            border-color: rgba(243, 156, 18, 0.42);
        }
        .top-strip-card.lean {
            border-color: rgba(241, 196, 15, 0.42);
        }
        .top-strip-card.pass {
            border-color: #343A46;
        }
        .top-strip-label {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.18rem 0.62rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .top-strip-label.side {
            background: rgba(46, 204, 113, 0.14);
            color: var(--positive);
            border: 1px solid rgba(46, 204, 113, 0.30);
        }
        .top-strip-label.total {
            background: rgba(243, 156, 18, 0.14);
            color: var(--totals);
            border: 1px solid rgba(243, 156, 18, 0.30);
        }
        .top-strip-label.lean {
            background: rgba(241, 196, 15, 0.14);
            color: var(--warning);
            border: 1px solid rgba(241, 196, 15, 0.30);
        }
        .top-strip-label.pass {
            background: rgba(139, 147, 167, 0.12);
            color: #B5BAC7;
            border: 1px solid rgba(139, 147, 167, 0.24);
        }
        .top-strip-title {
            color: var(--text);
            font-size: 1rem;
            font-weight: 760;
            margin-top: 0.75rem;
        }
        .top-strip-meta {
            color: var(--text-muted);
            font-size: 0.84rem;
            margin-top: 0.35rem;
            line-height: 1.45;
        }
        .top-strip-edge {
            color: var(--text);
            font-size: 1rem;
            font-weight: 780;
            margin-top: 0.6rem;
        }
        .top-play-card {
            border-radius: 18px;
            padding: 0.95rem 1rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        .top-play-card.strong {
            border-color: rgba(46, 204, 113, 0.56);
        }
        .top-play-card.lean {
            border-color: rgba(241, 196, 15, 0.50);
        }
        .top-play-card.pass {
            border-color: #343A46;
        }
        .top-play-card.negative {
            border-color: rgba(231, 76, 60, 0.50);
        }
        .best-bets-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
            margin-bottom: 1rem;
        }
        .best-bet-card {
            border-radius: 18px;
            padding: 1rem 1.05rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        .best-bet-card strong {
            color: var(--text);
        }
        .top-play-rank {
            color: var(--totals);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        .top-play-pick {
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 750;
            margin-top: 0.2rem;
        }
        .top-play-meta,
        .top-play-matchup,
        .top-play-stats {
            color: var(--text-muted);
            font-size: 0.86rem;
            margin-top: 0.25rem;
        }
        .top-play-stats {
            color: var(--text);
            font-weight: 650;
        }
        .toolbar-shell {
            margin: 0.75rem 0 1.15rem;
            padding: 0.8rem 0.95rem;
            border-radius: 18px;
            background: linear-gradient(180deg, #171B22 0%, #141821 100%);
            border: 1px solid var(--border);
        }
        .monitor-hero {
            margin: 0.25rem 0 1rem;
            padding: 1rem 1.05rem;
            border-radius: 18px;
            background:
                radial-gradient(circle at top left, rgba(243, 156, 18, 0.08), transparent 24%),
                radial-gradient(circle at bottom right, rgba(46, 204, 113, 0.06), transparent 24%),
                linear-gradient(180deg, #171B22 0%, #141821 100%);
            border: 1px solid var(--border);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        .monitor-kicker {
            color: var(--totals);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.72rem;
            font-weight: 800;
            margin-bottom: 0.4rem;
        }
        .monitor-title {
            color: var(--text);
            font-size: 1.4rem;
            font-weight: 800;
            margin: 0;
        }
        .monitor-copy {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: 0.35rem;
            line-height: 1.45;
        }
        .leader-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.7rem;
            margin: 0.35rem 0 1rem;
        }
        .leader-card {
            border-radius: 16px;
            padding: 0.9rem 0.95rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
        }
        .leader-rank {
            color: var(--totals);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
        }
        .leader-name {
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 760;
            margin-top: 0.32rem;
        }
        .leader-value {
            color: var(--positive);
            font-size: 1rem;
            font-weight: 800;
            margin-top: 0.36rem;
        }
        .leader-subtext {
            color: var(--text-muted);
            font-size: 0.82rem;
            margin-top: 0.25rem;
            line-height: 1.4;
        }
        .leader-groups-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 0.8rem;
            margin: 0.35rem 0 1rem;
        }
        .leader-group-card {
            border-radius: 18px;
            padding: 0.95rem 1rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        .leader-group-title {
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 780;
            margin-bottom: 0.18rem;
        }
        .leader-group-copy {
            color: var(--text-muted);
            font-size: 0.82rem;
            line-height: 1.4;
            margin-bottom: 0.7rem;
        }
        .leader-group-list {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
        }
        .leader-group-row {
            display: grid;
            grid-template-columns: 40px minmax(0, 1fr) auto;
            align-items: center;
            gap: 0.55rem;
            border-radius: 12px;
            padding: 0.46rem 0.55rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .leader-group-row.top3 {
            border-color: rgba(243, 156, 18, 0.28);
            box-shadow: inset 0 0 0 1px rgba(243, 156, 18, 0.05);
        }
        .leader-group-rank {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 24px;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            color: #C5CBD8;
            background: rgba(139, 147, 167, 0.12);
            border: 1px solid rgba(139, 147, 167, 0.22);
        }
        .leader-group-rank.rank-1 {
            color: #12161D;
            background: linear-gradient(180deg, #F6C65B 0%, #E6A93E 100%);
            border-color: rgba(246, 198, 91, 0.55);
        }
        .leader-group-rank.rank-2 {
            color: #12161D;
            background: linear-gradient(180deg, #DCE3ED 0%, #AEB7C7 100%);
            border-color: rgba(220, 227, 237, 0.45);
        }
        .leader-group-rank.rank-3 {
            color: #12161D;
            background: linear-gradient(180deg, #D89A68 0%, #B87946 100%);
            border-color: rgba(216, 154, 104, 0.45);
        }
        .leader-group-team {
            color: var(--text);
            font-size: 0.9rem;
            font-weight: 720;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .leader-group-metric {
            color: var(--positive);
            font-size: 0.86rem;
            font-weight: 780;
            text-align: right;
            white-space: nowrap;
        }
        .monitor-summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.75rem;
            margin: 0.3rem 0 1rem;
        }
        .monitor-summary-card {
            border-radius: 16px;
            padding: 0.95rem 1rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
        }
        .monitor-summary-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        .monitor-summary-team {
            color: var(--text);
            font-size: 1rem;
            font-weight: 780;
            margin-top: 0.35rem;
        }
        .monitor-summary-value {
            color: var(--totals);
            font-size: 0.88rem;
            font-weight: 720;
            margin-top: 0.22rem;
        }
        .monitor-layout-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
            gap: 0.9rem;
            align-items: start;
            margin: 0.35rem 0 1rem;
        }
        .monitor-panel {
            border-radius: 18px;
            padding: 0.95rem 1rem;
            background: linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
        }
        .monitor-panel-title {
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 780;
            margin-bottom: 0.18rem;
        }
        .monitor-panel-copy {
            color: var(--text-muted);
            font-size: 0.84rem;
            line-height: 1.45;
            margin-bottom: 0.7rem;
        }
        .monitor-notes {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.7rem;
            margin: 0.35rem 0 1rem;
        }
        .monitor-note-card {
            border-radius: 14px;
            padding: 0.85rem 0.9rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .monitor-note-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .monitor-note-value {
            color: var(--text);
            font-size: 0.94rem;
            font-weight: 720;
            margin-top: 0.24rem;
            line-height: 1.4;
        }
        .monitor-expander-copy {
            color: var(--text-muted);
            font-size: 0.84rem;
            margin-bottom: 0.65rem;
            line-height: 1.45;
        }
        .team-profile-card {
            border-radius: 18px;
            padding: 1rem 1.05rem;
            background:
                radial-gradient(circle at top left, rgba(46, 204, 113, 0.07), transparent 26%),
                radial-gradient(circle at bottom right, rgba(243, 156, 18, 0.07), transparent 24%),
                linear-gradient(180deg, #1C1F26 0%, #181B22 100%);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
            margin: 0.3rem 0 1rem;
        }
        .team-profile-kicker {
            color: var(--totals);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
        }
        .team-profile-title {
            color: var(--text);
            font-size: 1.35rem;
            font-weight: 800;
            margin-top: 0.28rem;
        }
        .team-profile-copy {
            color: var(--text-muted);
            font-size: 0.88rem;
            line-height: 1.45;
            margin-top: 0.35rem;
        }
        .team-profile-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.7rem;
            margin-top: 0.85rem;
        }
        .team-profile-metric {
            border-radius: 14px;
            padding: 0.78rem 0.85rem;
            background: linear-gradient(180deg, #20242D 0%, #1A1E26 100%);
            border: 1px solid #2A303A;
        }
        .team-profile-label {
            color: var(--text-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .team-profile-value {
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 760;
            margin-top: 0.25rem;
        }
        .stDataFrame, div[data-testid="stDataEditor"] {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid var(--border);
        }
        div[data-testid="stContainer"] {
            background-color: transparent;
        }
        .stButton > button, .stDownloadButton > button {
            background: linear-gradient(180deg, #242934 0%, #1E232C 100%);
            color: var(--text);
            border: 1px solid #3A404C;
            border-radius: 12px;
            font-weight: 600;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            border-color: var(--totals);
            color: #FFFFFF;
            box-shadow: 0 0 0 1px rgba(243, 156, 18, 0.18);
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="base-input"] > div {
            background-color: #1C1F26 !important;
            border-color: #323844 !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] input,
        div[data-baseweb="base-input"] input {
            color: var(--text) !important;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--text-muted) !important;
        }
        [data-testid="stAlert"] {
            background: #1C1F26;
            border: 1px solid var(--border);
        }
        [data-testid="stToolbar"] {
            visibility: hidden;
        }
        @media (max-width: 900px) {
            .best-bets-grid,
            .bet-slip-grid,
            .market-strip,
            .board-view-grid,
            .monitor-layout-grid,
            .global-status-grid {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 720px) {
            .block-container {
                padding-top: 0.85rem;
                padding-bottom: 1.3rem;
                padding-left: 0.7rem;
                padding-right: 0.7rem;
            }
            .hero-panel,
            .section-panel,
            .board-card,
            .top-strip-card,
            .best-bet-card,
            .monitor-hero,
            .toolbar-shell,
            .global-status-strip {
                border-radius: 16px;
            }
            .hero-panel,
            .section-panel,
            .monitor-hero,
            .global-status-strip,
            .toolbar-shell {
                padding-left: 0.8rem;
                padding-right: 0.8rem;
            }
            .hero-grid {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }
            .hero-title {
                font-size: 1.75rem;
                line-height: 1.1;
            }
            .hero-subtitle,
            .monitor-copy,
            .section-subtitle,
            .toolbar-note {
                font-size: 0.84rem;
            }
            .sticky-summary-shell {
                position: static;
            }
            .board-card {
                padding: 0.7rem 0.75rem 0.78rem;
            }
            .board-topline {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.45rem;
                margin-bottom: 0.65rem;
            }
            .board-status-badge {
                margin-left: 0;
            }
            .board-matchup {
                font-size: 1.12rem;
                line-height: 1.2;
            }
            .board-subtle,
            .card-note,
            .bet-slip-summary,
            .top-strip-meta,
            .top-play-meta,
            .top-play-matchup {
                font-size: 0.8rem;
            }
            .board-status-row,
            .chips-row,
            .card-pill-row,
            .freshness-pills {
                gap: 0.35rem;
            }
            .signal-badge,
            .favorite-badge,
            .angle-badge,
            .freshness-pill {
                font-size: 0.69rem;
                line-height: 1.2;
            }
            .score-ribbon,
            .bet-slip-card,
            .board-view-card,
            .market-cell,
            .meta-pill,
            .team-profile-metric,
            .monitor-note-card {
                padding: 0.72rem 0.78rem;
            }
            .score-ribbon-value,
            .top-play-pick,
            .top-strip-title,
            .leader-name {
                font-size: 0.96rem;
            }
            .probability-line {
                grid-template-columns: minmax(84px, 1fr) 52px minmax(92px, 1fr);
                gap: 0.45rem;
                padding: 0.52rem 0.6rem;
            }
            .probability-team,
            .probability-value,
            .market-value,
            .meta-value,
            .team-profile-value {
                font-size: 0.84rem;
            }
            .card-section-divider {
                margin-top: 0.65rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    st.markdown(
        f"""
        <div class="hero-panel">
            <div class="hero-grid">
                <div>
                    <div class="hero-kicker">Probability-first MLB board</div>
                    <h1 class="hero-title">MLB Matchup Dashboard</h1>
                    <p class="hero-subtitle">
                        Sportsbook-style daily board with editable model inputs, projected scoring,
                        and live win-probability outputs powered by {DEFAULT_SIMS:,} simulations per game.
                    </p>
                </div>
                <div class="hero-sidecar">
                    <div class="hero-sidecar-label">Board Overview</div>
                    <div class="hero-sidecar-value">Win probabilities and run environment</div>
                    <div class="hero-sidecar-copy">
                        Update pitchers, lineup strength, bullpen fatigue, or weather inputs and the
                        dashboard recalculates automatically without changing the underlying model logic.
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_odds_api_key():
    """
    Load the Odds API key from Streamlit secrets first, then environment vars.

    Streamlit secrets are the most reliable source for dashboard apps because
    they persist across terminal restarts. The environment variable remains as
    a backward-compatible fallback for local shells and ad hoc runs.
    """
    try:
        odds_api_key = st.secrets[ODDS_API_KEY_ENV_VAR]
    except Exception:
        odds_api_key = os.getenv(ODDS_API_KEY_ENV_VAR)
    return odds_api_key


def render_odds_config():
    config_col_1, config_col_2, config_col_3, config_col_4 = st.columns(4)
    odds_api_key = get_odds_api_key()
    with config_col_1:
        api_key_present = bool(odds_api_key)
        st.text_input(
            "ODDS_API_KEY",
            value="Loaded" if api_key_present else "Not set",
            disabled=True,
            help="Loaded from Streamlit secrets first, then environment variables as a fallback.",
        )
    with config_col_2:
        st.text_input("Sport", value=ODDS_API_SPORT, disabled=True)
    with config_col_3:
        st.text_input("Region", value=ODDS_API_REGION, disabled=True)
    with config_col_4:
        st.text_input("Markets", value=ODDS_API_MARKETS, disabled=True)

    if not api_key_present:
        st.warning(
            "Odds API key not found. Add ODDS_API_KEY to either:\n"
            "- .streamlit/secrets.toml\n"
            "or\n"
            "- environment variables."
        )


def render_simulation_config():
    st.number_input(
        "Run Dispersion",
        min_value=RUN_DISPERSION_MIN,
        max_value=RUN_DISPERSION_MAX,
        value=float(st.session_state.get("run_dispersion", DEFAULT_RUN_DISPERSION)),
        step=RUN_DISPERSION_STEP,
        key="run_dispersion",
        help=(
            "Negative Binomial size parameter used in the run simulation. "
            "Lower values create wider scoring variance, while higher values "
            "move the model closer to Poisson."
        ),
    )
    st.caption("Variance scales approximately as mu + mu^2 / r, where r is the run dispersion.")


@st.cache_data(show_spinner=False)
def load_pitcher_ratings(data_mode):
    try:
        if data_mode == "live":
            raise NotImplementedError("Live pitcher ratings are not implemented yet.")
        pitcher_ratings = pd.read_csv("data/pitcher_ratings.csv")
    except Exception:
        pitcher_ratings = pd.read_csv("data/pitcher_ratings.csv")

    for required_col, default_value in {
        "pitcher_name": "",
        "pitcher_rating": 1.00,
        "fip": None,
        "throws": "",
    }.items():
        if required_col not in pitcher_ratings.columns:
            pitcher_ratings[required_col] = default_value

    return pitcher_ratings


@st.cache_data(show_spinner=False)
def load_lineup_data():
    try:
        hitter_ratings = load_hitter_ratings()
    except Exception:
        hitter_ratings = pd.DataFrame(columns=["player_name", "hitter_rating"])

    try:
        projected_lineups = load_projected_lineups()
    except Exception:
        projected_lineups = pd.DataFrame(columns=["team", "player_name"])

    return hitter_ratings, projected_lineups


@st.cache_data(show_spinner=False)
def load_today_matchups_cached(data_mode):
    return load_today_matchups(data_mode=data_mode)


def get_default_lineup_adjustment(team_name, hitter_ratings, projected_lineups):
    return calculate_lineup_adjustment(team_name, hitter_ratings, projected_lineups)


def get_default_pitcher_rating(pitcher_name, pitcher_ratings):
    if not pitcher_name or pd.isna(pitcher_name):
        return 1.00

    pitcher_row = pitcher_ratings.loc[pitcher_ratings["pitcher_name"] == pitcher_name]
    if pitcher_row.empty:
        return 1.00

    rating = pitcher_row.iloc[0]["pitcher_rating"]
    if pd.isna(rating):
        return 1.00

    return float(rating)


def get_pitcher_throws(pitcher_name, pitcher_ratings):
    if not pitcher_name or pd.isna(pitcher_name):
        return ""

    pitcher_row = pitcher_ratings.loc[pitcher_ratings["pitcher_name"] == pitcher_name]
    if pitcher_row.empty:
        return ""

    throws = pitcher_row.iloc[0]["throws"]
    if pd.isna(throws):
        return ""

    return str(throws).strip().upper()


def get_default_weather(home_team_name, stadium_locations):
    weather = get_weather_for_team(
        home_team_name,
        stadium_locations,
        data_mode=DATA_MODE,
    )

    return {
        "Temp": int(weather.get("temperature_f", 72)),
        "Wind": float(weather.get("wind_factor", 1.00)),
    }

def choose_preferred_bookmaker(bookmakers):
    if not bookmakers:
        return None

    bookmaker_lookup = {
        bookmaker.get("key"): bookmaker
        for bookmaker in bookmakers
        if bookmaker.get("key")
    }

    for bookmaker_key in PREFERRED_SPORTSBOOKS:
        if bookmaker_key in bookmaker_lookup:
            return bookmaker_lookup[bookmaker_key]

    return bookmakers[0]


def parse_bookmaker_h2h_market(bookmaker, away_team, home_team):
    best_prices = {
        "away_moneyline": None,
        "home_moneyline": None,
    }

    if bookmaker is None:
        return best_prices

    for market in bookmaker.get("markets", []):
        if market.get("key") != "h2h":
            continue

        for outcome in market.get("outcomes", []):
            outcome_name = outcome.get("name")
            outcome_price = outcome.get("price")
            if outcome_name == away_team and outcome_price is not None:
                best_prices["away_moneyline"] = int(float(outcome_price))
            elif outcome_name == home_team and outcome_price is not None:
                best_prices["home_moneyline"] = int(float(outcome_price))

        return best_prices

    return best_prices


def parse_bookmaker_totals_market(bookmaker):
    best_prices = {
        "total_line": None,
        "over_price": None,
        "under_price": None,
    }

    if bookmaker is None:
        return best_prices

    for market in bookmaker.get("markets", []):
        if market.get("key") != "totals":
            continue

        over_outcome = next(
            (outcome for outcome in market.get("outcomes", []) if outcome.get("name") == "Over"),
            None,
        )
        under_outcome = next(
            (outcome for outcome in market.get("outcomes", []) if outcome.get("name") == "Under"),
            None,
        )
        if over_outcome is None and under_outcome is None:
            continue

        line_point = None
        if over_outcome is not None:
            line_point = over_outcome.get("point")
            over_price = over_outcome.get("price")
            best_prices["over_price"] = int(float(over_price)) if over_price is not None else None
        if under_outcome is not None:
            if line_point is None:
                line_point = under_outcome.get("point")
            under_price = under_outcome.get("price")
            best_prices["under_price"] = int(float(under_price)) if under_price is not None else None
        if line_point is not None:
            best_prices["total_line"] = float(line_point)

        return best_prices

    return best_prices


@st.cache_data(show_spinner=False, ttl=300)
def fetch_live_odds(sport_key=ODDS_API_SPORT, region=ODDS_API_REGION, markets=ODDS_API_MARKETS):
    # Reuse the same key-loading order as the UI so Streamlit secrets work even
    # after the terminal session or environment has been reset.
    api_key = get_odds_api_key()
    if not api_key:
        raise ValueError(
            f"Missing API key. Add {ODDS_API_KEY_ENV_VAR} to Streamlit secrets or your environment."
        )

    response = requests.get(
        f"{ODDS_API_BASE_URL}/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": region,
            "markets": markets,
            "oddsFormat": "american",
        },
        timeout=20,
    )
    response.raise_for_status()

    odds_rows = {}
    for event in response.json():
        away_team = event.get("away_team")
        home_team = event.get("home_team")
        if not away_team or not home_team:
            continue

        bookmakers = event.get("bookmakers", [])
        team_key = (normalize_team_name(away_team), normalize_team_name(home_team))
        selected_bookmaker = choose_preferred_bookmaker(bookmakers)
        h2h_prices = parse_bookmaker_h2h_market(selected_bookmaker, away_team, home_team)
        totals_prices = parse_bookmaker_totals_market(selected_bookmaker)
        consensus_prices = build_market_consensus(bookmakers, away_team, home_team)
        odds_rows[team_key] = {
            **h2h_prices,
            **totals_prices,
            **consensus_prices,
            "sportsbook": selected_bookmaker.get("title") if selected_bookmaker else None,
        }

    return odds_rows


def apply_live_odds_to_board(board_inputs, odds_map):
    updated_board = board_inputs.copy()
    matched_games = 0

    for idx, row in updated_board.iterrows():
        matchup_key = (normalize_team_name(row["Away"]), normalize_team_name(row["Home"]))
        odds_row = odds_map.get(matchup_key)
        if odds_row is None:
            continue

        matched_games += 1
        updated_board.at[idx, "Away Moneyline"] = odds_row["away_moneyline"]
        updated_board.at[idx, "Home Moneyline"] = odds_row["home_moneyline"]
        updated_board.at[idx, "Total Line"] = odds_row["total_line"]
        updated_board.at[idx, "Over Price"] = odds_row["over_price"]
        updated_board.at[idx, "Under Price"] = odds_row["under_price"]
        updated_board.at[idx, "Sportsbook"] = odds_row.get("sportsbook")

    return updated_board, matched_games


def american_odds_to_implied_prob(odds_value):
    if odds_value is None or pd.isna(odds_value):
        return None

    try:
        odds = float(odds_value)
    except (TypeError, ValueError):
        return None

    if odds == 0:
        return None

    if odds > 0:
        return 100.0 / (odds + 100.0)

    return abs(odds) / (abs(odds) + 100.0)


def calculate_no_vig_probs(away_odds, home_odds):
    away_raw = american_odds_to_implied_prob(away_odds)
    home_raw = american_odds_to_implied_prob(home_odds)

    if away_raw is None or home_raw is None:
        return away_raw, home_raw, None, None, None

    overround = away_raw + home_raw
    if overround <= 0:
        return away_raw, home_raw, None, None, None

    away_no_vig = away_raw / overround
    home_no_vig = home_raw / overround
    vig = overround - 1.0
    return away_raw, home_raw, away_no_vig, home_no_vig, vig


def format_moneyline(odds_value):
    if odds_value is None or pd.isna(odds_value):
        return "N/A"

    try:
        odds = int(float(odds_value))
    except (TypeError, ValueError):
        return "N/A"

    if odds > 0:
        return f"+{odds}"
    return str(odds)


def american_odds_profit(odds_value):
    if odds_value is None or pd.isna(odds_value):
        return None

    try:
        odds = float(odds_value)
    except (TypeError, ValueError):
        return None

    if odds == 0:
        return None
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


def probability_to_american_odds(probability):
    if probability is None or pd.isna(probability):
        return None

    prob = float(probability)
    if prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return int(round(-100 * prob / (1 - prob)))
    return int(round(100 * (1 - prob) / prob))


def calculate_expected_value(model_win_prob, odds_value):
    if model_win_prob is None or pd.isna(model_win_prob):
        return None

    profit = american_odds_profit(odds_value)
    if profit is None:
        return None

    win_prob = float(model_win_prob)
    lose_prob = 1.0 - win_prob
    return (win_prob * profit) - lose_prob


def calculate_total_probabilities(projected_total, total_line, logistic_k=TOTALS_LOGISTIC_K):
    if projected_total is None or total_line is None or pd.isna(projected_total) or pd.isna(total_line):
        return None, None, None

    difference = float(projected_total) - float(total_line)
    over_prob = 1.0 / (1.0 + math.exp(-difference * logistic_k))
    under_prob = 1.0 - over_prob
    return over_prob, under_prob, difference


def calculate_totals_market_probs(over_price, under_price):
    over_raw = american_odds_to_implied_prob(over_price)
    under_raw = american_odds_to_implied_prob(under_price)
    over_no_vig = None
    under_no_vig = None
    total_hold = None

    if over_raw is not None and under_raw is not None:
        over_raw, under_raw, over_no_vig, under_no_vig, total_hold = calculate_no_vig_probs(
            over_price,
            under_price,
        )

    over_market_prob = over_no_vig if over_no_vig is not None else over_raw
    under_market_prob = under_no_vig if under_no_vig is not None else under_raw

    return {
        "over_raw": over_raw,
        "under_raw": under_raw,
        "over_market_prob": over_market_prob,
        "under_market_prob": under_market_prob,
        "total_hold": total_hold,
    }


def calculate_total_bet_signal(
    over_edge_pct,
    under_edge_pct,
    over_ev,
    under_ev,
    strong_ev_threshold=STRONG_TOTAL_EV_THRESHOLD,
    strong_edge_threshold=STRONG_TOTAL_EDGE_THRESHOLD,
    lean_ev_threshold=LEAN_TOTAL_EV_THRESHOLD,
):
    candidates = [
        {"side": "Over", "edge": over_edge_pct, "ev": over_ev},
        {"side": "Under", "edge": under_edge_pct, "ev": under_ev},
    ]

    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate["ev"] is not None and not pd.isna(candidate["ev"]) and candidate["ev"] > 0
    ]
    if not valid_candidates:
        return "Pass", "Pass", None, None

    best_candidate = max(
        valid_candidates,
        key=lambda candidate: (
            candidate["ev"],
            candidate["edge"] if candidate["edge"] is not None else float("-inf"),
        ),
    )
    best_edge = best_candidate["edge"]
    best_ev = best_candidate["ev"]

    if best_ev >= strong_ev_threshold and best_edge is not None and best_edge >= strong_edge_threshold:
        return best_candidate["side"], "Strong Bet", best_edge, best_ev
    if best_ev >= lean_ev_threshold and best_edge is not None and best_edge > 0:
        return best_candidate["side"], "Lean", best_edge, best_ev
    return "Pass", "Pass", best_edge, best_ev


def build_market_consensus(bookmakers, away_team, home_team):
    valid_book_probabilities = []
    valid_hold_values = []

    for bookmaker in bookmakers or []:
        h2h_prices = parse_bookmaker_h2h_market(bookmaker, away_team, home_team)
        away_price = h2h_prices.get("away_moneyline")
        home_price = h2h_prices.get("home_moneyline")
        if away_price is None or home_price is None:
            continue

        away_raw, home_raw, away_no_vig, home_no_vig, vig = calculate_no_vig_probs(
            away_price,
            home_price,
        )
        if away_no_vig is None or home_no_vig is None:
            continue

        valid_book_probabilities.append(
            {
                "sportsbook": bookmaker.get("title") or bookmaker.get("key"),
                "away_no_vig": away_no_vig,
                "home_no_vig": home_no_vig,
            }
        )
        if vig is not None:
            valid_hold_values.append(vig)

    if not valid_book_probabilities:
        return {
            "away_consensus_prob": None,
            "home_consensus_prob": None,
            "consensus_hold_avg": None,
            "consensus_books_used": 0,
            "away_fair_ml": None,
            "home_fair_ml": None,
        }

    away_consensus_prob = sum(item["away_no_vig"] for item in valid_book_probabilities) / len(
        valid_book_probabilities
    )
    home_consensus_prob = 1.0 - away_consensus_prob
    consensus_hold_avg = sum(valid_hold_values) / len(valid_hold_values) if valid_hold_values else None

    return {
        "away_consensus_prob": away_consensus_prob,
        "home_consensus_prob": home_consensus_prob,
        "consensus_hold_avg": consensus_hold_avg,
        "consensus_books_used": len(valid_book_probabilities),
        "away_fair_ml": probability_to_american_odds(away_consensus_prob),
        "home_fair_ml": probability_to_american_odds(home_consensus_prob),
    }


def calculate_bet_signal(
    away_edge_pct,
    home_edge_pct,
    away_ev,
    home_ev,
    strong_ev_threshold=STRONG_BET_EV_THRESHOLD,
    strong_edge_threshold=STRONG_BET_EDGE_THRESHOLD,
    lean_ev_threshold=LEAN_BET_EV_THRESHOLD,
    lean_edge_threshold=LEAN_BET_EDGE_THRESHOLD,
):
    candidates = [
        {"side": "Away", "edge": away_edge_pct, "ev": away_ev},
        {"side": "Home", "edge": home_edge_pct, "ev": home_ev},
    ]

    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate["ev"] is not None and not pd.isna(candidate["ev"]) and candidate["ev"] > 0
    ]
    if not valid_candidates:
        return "Pass", "Pass", None, None

    best_candidate = max(
        valid_candidates,
        key=lambda candidate: (
            candidate["ev"],
            candidate["edge"] if candidate["edge"] is not None else float("-inf"),
        ),
    )

    best_edge = best_candidate["edge"]
    best_ev = best_candidate["ev"]

    if best_ev >= strong_ev_threshold and best_edge is not None and best_edge >= strong_edge_threshold:
        return best_candidate["side"], "Strong Bet", best_edge, best_ev

    if best_ev >= lean_ev_threshold and best_edge is not None and best_edge > 0:
        return best_candidate["side"], "Lean", best_edge, best_ev

    return "Pass", "Pass", best_edge, best_ev


def build_daily_input_table(
    matchups,
    pitcher_ratings,
    stadium_locations,
    hitter_ratings,
    projected_lineups,
):
    rows = []

    for _, matchup in matchups.iterrows():
        away_team_name = matchup.get("away_team", "")
        home_team_name = matchup.get("home_team", "")

        if away_team_name not in team_ratings.index or home_team_name not in team_ratings.index:
            continue

        away_pitcher_name = matchup.get("away_pitcher", "")
        home_pitcher_name = matchup.get("home_pitcher", "")

        if pd.isna(away_pitcher_name):
            away_pitcher_name = ""

        if pd.isna(home_pitcher_name):
            home_pitcher_name = ""

        default_weather = get_default_weather(home_team_name, stadium_locations)

        rows.append(
            {
                "Away": away_team_name,
                "Home": home_team_name,
                "Away Pitcher": away_pitcher_name,
                "Home Pitcher": home_pitcher_name,
                "A Hand": get_pitcher_throws(away_pitcher_name, pitcher_ratings),
                "H Hand": get_pitcher_throws(home_pitcher_name, pitcher_ratings),
                "Away SP": get_default_pitcher_rating(away_pitcher_name, pitcher_ratings),
                "Home SP": get_default_pitcher_rating(home_pitcher_name, pitcher_ratings),
                "Away BP Fatigue": 0.00,
                "Home BP Fatigue": 0.00,
                "Away Lineup": get_default_lineup_adjustment(
                    away_team_name,
                    hitter_ratings,
                    projected_lineups,
                ),
                "Home Lineup": get_default_lineup_adjustment(
                    home_team_name,
                    hitter_ratings,
                    projected_lineups,
                ),
                "Manual Wx": False,
                "Temp": default_weather["Temp"],
                "Wind": default_weather["Wind"],
                "Away Moneyline": None,
                "Home Moneyline": None,
                "Total Line": None,
                "Over Price": None,
                "Under Price": None,
                "Sportsbook": None,
            }
        )

    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


@st.cache_data(show_spinner=False)
def load_stadium_locations_cached(data_mode):
    return load_stadium_locations(data_mode=data_mode)


def clear_app_caches():
    load_team_ratings_cached.clear()
    load_pitcher_ratings.clear()
    load_lineup_data.clear()
    load_today_matchups_cached.clear()
    load_stadium_locations_cached.clear()
    clear_tracked_bet_caches()
    fetch_live_odds.clear()


def set_board_timestamp(session_key):
    st.session_state[session_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_board_timestamp(session_key):
    timestamp_value = st.session_state.get(session_key)
    if not timestamp_value:
        return "Waiting"
    return str(timestamp_value)


def render_global_status_strip():
    status_items = [
        ("Board Inputs", format_board_timestamp("board_inputs_last_updated")),
        ("Odds", format_board_timestamp("odds_last_updated")),
        ("Simulations", format_board_timestamp("simulation_last_updated")),
        ("Model Data", format_board_timestamp("model_data_last_updated")),
    ]
    chips_html = "".join(
        dedent(
            f"""
            <div class="global-status-chip">
                <div class="global-status-label">{label}</div>
                <div class="global-status-value">{value}</div>
            </div>
            """
        ).strip()
        for label, value in status_items
    )
    st.markdown(
        dedent(
            f"""
            <div class="global-status-strip">
                <div class="global-status-grid">
                    <div>
                        <div class="global-status-title">Workbook Status</div>
                        <div class="global-status-copy">Shared freshness ribbon for the board, drivers, standings, and performance workflow.</div>
                    </div>
                    {chips_html}
                </div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def render_tab_intro(kicker, title, copy):
    st.markdown(
        dedent(
            f"""
            <div class="monitor-hero">
                <div class="monitor-kicker">{kicker}</div>
                <div class="monitor-title">{title}</div>
                <div class="monitor-copy">{copy}</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _add_snapshot_metadata(snapshot_df, snapshot_timestamp, run_dispersion, snapshot_type):
    snapshot_copy = snapshot_df.copy()
    required_columns = [
        "Away",
        "Home",
        "Sportsbook",
        "Best Bet",
        "Bet Flag",
        "Best Total Bet",
        "Total Bet Flag",
    ]
    for column_name in required_columns:
        if column_name not in snapshot_copy.columns:
            snapshot_copy[column_name] = None
    snapshot_copy["snapshot_timestamp"] = snapshot_timestamp
    snapshot_copy["snapshot_date"] = snapshot_timestamp[:10]
    snapshot_copy["run_dispersion"] = float(run_dispersion)
    snapshot_copy["data_mode"] = DATA_MODE
    snapshot_copy["snapshot_type"] = snapshot_type
    snapshot_copy["grading_status"] = "ungraded"
    return snapshot_copy


def save_board_snapshot(display_df, run_dispersion, history_dir=HISTORY_DIR):
    history_path = ensure_history_dir(history_dir)
    snapshot_now = datetime.now()
    timestamp = snapshot_now.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_slug = snapshot_now.strftime("%Y%m%d_%H%M%S")
    snapshot_df = _add_snapshot_metadata(display_df, timestamp, run_dispersion, "board")
    file_path = os.path.join(history_path, f"board_snapshot_{timestamp_slug}.csv")
    snapshot_df.to_csv(file_path, index=False)
    persist_snapshot_rows_to_db(snapshot_df)
    return file_path


def save_top_plays_snapshot(top_plays_df, run_dispersion, history_dir=HISTORY_DIR):
    if top_plays_df is None or top_plays_df.empty:
        return None

    history_path = ensure_history_dir(history_dir)
    snapshot_now = datetime.now()
    timestamp = snapshot_now.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_slug = snapshot_now.strftime("%Y%m%d_%H%M%S")
    snapshot_df = _add_snapshot_metadata(top_plays_df, timestamp, run_dispersion, "top_plays")
    file_path = os.path.join(history_path, f"top_plays_snapshot_{timestamp_slug}.csv")
    snapshot_df.to_csv(file_path, index=False)
    return file_path


def reload_automated_inputs(force_refresh=False):
    if force_refresh:
        clear_app_caches()

    matchups = load_today_matchups_cached(data_mode=DATA_MODE)
    pitcher_ratings = load_pitcher_ratings(DATA_MODE)
    stadium_locations = load_stadium_locations_cached(DATA_MODE)
    hitter_ratings, projected_lineups = load_lineup_data()

    st.session_state["daily_matchups"] = matchups
    st.session_state["pitcher_ratings"] = pitcher_ratings
    st.session_state["stadium_locations"] = stadium_locations
    st.session_state["hitter_ratings"] = hitter_ratings
    st.session_state["projected_lineups"] = projected_lineups
    st.session_state["live_odds_market_data"] = {}
    st.session_state["daily_board_inputs"] = build_daily_input_table(
        matchups,
        pitcher_ratings,
        stadium_locations,
        hitter_ratings,
        projected_lineups,
    )
    set_board_timestamp("board_inputs_last_updated")


@st.cache_data(show_spinner=False)
def build_display_dataframe(
    daily_board_inputs,
    pitcher_ratings,
    team_ratings,
    live_odds_market_data=None,
    run_dispersion=DEFAULT_RUN_DISPERSION,
    sims=DEFAULT_SIMS,
):
    # This is the main expensive board computation. Caching here prevents
    # Streamlit reruns from re-simulating every matchup unless one of the
    # simulation-driving inputs actually changes.
    display_rows = []

    for _, row in daily_board_inputs.iterrows():
        away_pitcher_name = row["Away Pitcher"]
        home_pitcher_name = row["Home Pitcher"]

        away_pitcher_throws = get_pitcher_throws(away_pitcher_name, pitcher_ratings)
        home_pitcher_throws = get_pitcher_throws(home_pitcher_name, pitcher_ratings)

        row_temperature_f = float(row["Temp"]) if bool(row["Manual Wx"]) else None
        row_wind_factor = float(row["Wind"]) if bool(row["Manual Wx"]) else None

        matchup_results = simulate_matchup(
            away_team=row["Away"],
            home_team=row["Home"],
            away_starter_rating=float(row["Away SP"]),
            home_starter_rating=float(row["Home SP"]),
            away_pitcher_throws=away_pitcher_throws or None,
            home_pitcher_throws=home_pitcher_throws or None,
            away_bullpen_fatigue=float(row["Away BP Fatigue"]),
            home_bullpen_fatigue=float(row["Home BP Fatigue"]),
            away_lineup_adjustment=float(row["Away Lineup"]),
            home_lineup_adjustment=float(row["Home Lineup"]),
            temperature_f=row_temperature_f,
            wind_factor=row_wind_factor,
            sims=sims,
            run_dispersion=run_dispersion,
            teams=team_ratings,
        )

        away_win_pct = round(matchup_results["away_win_prob"] * 100, 1)
        home_win_pct = round(matchup_results["home_win_prob"] * 100, 1)
        matchup_key = (normalize_team_name(row["Away"]), normalize_team_name(row["Home"]))
        market_data = (live_odds_market_data or {}).get(matchup_key, {})

        (
            away_implied_prob,
            home_implied_prob,
            away_no_vig_prob,
            home_no_vig_prob,
            _vig,
        ) = calculate_no_vig_probs(
            row.get("Away Moneyline"),
            row.get("Home Moneyline"),
        )

        away_implied_pct = round(away_implied_prob * 100, 1) if away_implied_prob is not None else None
        home_implied_pct = round(home_implied_prob * 100, 1) if home_implied_prob is not None else None
        away_no_vig_pct = round(away_no_vig_prob * 100, 1) if away_no_vig_prob is not None else None
        home_no_vig_pct = round(home_no_vig_prob * 100, 1) if home_no_vig_prob is not None else None
        hold_pct = round(_vig * 100, 1) if _vig is not None else None

        away_consensus_prob = market_data.get("away_consensus_prob")
        home_consensus_prob = market_data.get("home_consensus_prob")
        away_consensus_pct = round(float(away_consensus_prob) * 100, 1) if away_consensus_prob is not None else None
        home_consensus_pct = round(float(home_consensus_prob) * 100, 1) if home_consensus_prob is not None else None

        consensus_hold_avg = market_data.get("consensus_hold_avg")
        consensus_hold_pct = round(float(consensus_hold_avg) * 100, 1) if consensus_hold_avg is not None else None
        consensus_books_used = market_data.get("consensus_books_used")
        away_fair_ml = market_data.get("away_fair_ml")
        home_fair_ml = market_data.get("home_fair_ml")

        away_edge_pct = round(away_win_pct - away_consensus_pct, 1) if away_consensus_pct is not None else None
        home_edge_pct = round(home_win_pct - home_consensus_pct, 1) if home_consensus_pct is not None else None

        away_ev = calculate_expected_value(matchup_results["away_win_prob"], row.get("Away Moneyline"))
        home_ev = calculate_expected_value(matchup_results["home_win_prob"], row.get("Home Moneyline"))
        away_ev_pct = round(away_ev * 100, 1) if away_ev is not None else None
        home_ev_pct = round(home_ev * 100, 1) if home_ev is not None else None

        projected_total = round(matchup_results["away_lambda"] + matchup_results["home_lambda"], 2)
        total_line = row.get("Total Line")
        over_prob, under_prob, total_difference = calculate_total_probabilities(projected_total, total_line)

        totals_market = calculate_totals_market_probs(
            row.get("Over Price"),
            row.get("Under Price"),
        )
        over_market_prob = totals_market["over_market_prob"]
        under_market_prob = totals_market["under_market_prob"]

        over_edge_pct = (
            round((over_prob - over_market_prob) * 100, 1)
            if over_prob is not None and over_market_prob is not None
            else None
        )
        under_edge_pct = (
            round((under_prob - under_market_prob) * 100, 1)
            if under_prob is not None and under_market_prob is not None
            else None
        )

        over_ev = calculate_expected_value(over_prob, row.get("Over Price")) if over_prob is not None else None
        under_ev = calculate_expected_value(under_prob, row.get("Under Price")) if under_prob is not None else None
        over_ev_pct = round(over_ev * 100, 1) if over_ev is not None else None
        under_ev_pct = round(under_ev * 100, 1) if under_ev is not None else None

        best_total_bet, total_bet_flag, _, _ = calculate_total_bet_signal(
            over_edge_pct,
            under_edge_pct,
            over_ev,
            under_ev,
        )
        best_bet, bet_flag, _, _ = calculate_bet_signal(
            away_edge_pct,
            home_edge_pct,
            away_ev,
            home_ev,
        )

        display_row = row.to_dict()
        display_row["A Hand"] = away_pitcher_throws
        display_row["H Hand"] = home_pitcher_throws
        display_row["Away Runs"] = round(matchup_results["away_lambda"], 2)
        display_row["Home Runs"] = round(matchup_results["home_lambda"], 2)
        display_row["Away Win"] = away_win_pct
        display_row["Home Win"] = home_win_pct
        display_row["Away Implied %"] = away_implied_pct
        display_row["Home Implied %"] = home_implied_pct
        display_row["Away No-Vig %"] = away_no_vig_pct
        display_row["Home No-Vig %"] = home_no_vig_pct
        display_row["Hold %"] = hold_pct
        display_row["Away Consensus %"] = away_consensus_pct
        display_row["Home Consensus %"] = home_consensus_pct
        display_row["Consensus Hold Avg"] = consensus_hold_pct
        display_row["Consensus Books Used"] = consensus_books_used
        display_row["Away Fair ML"] = away_fair_ml
        display_row["Home Fair ML"] = home_fair_ml
        display_row["Away Edge %"] = away_edge_pct
        display_row["Home Edge %"] = home_edge_pct
        display_row["Away EV"] = away_ev_pct
        display_row["Home EV"] = home_ev_pct
        display_row["Projected Total"] = projected_total
        display_row["Total Diff"] = round(total_difference, 2) if total_difference is not None else None
        display_row["Over Edge %"] = over_edge_pct
        display_row["Under Edge %"] = under_edge_pct
        display_row["Over EV"] = over_ev_pct
        display_row["Under EV"] = under_ev_pct
        display_row["Best Total Bet"] = best_total_bet
        display_row["Total Bet Flag"] = total_bet_flag
        display_row["Favorite"] = row["Home"] if home_win_pct >= away_win_pct else row["Away"]
        display_row["Win Edge"] = round(abs(home_win_pct - away_win_pct), 1)
        if best_bet == "Away":
            display_row["Best Bet"] = row["Away"]
        elif best_bet == "Home":
            display_row["Best Bet"] = row["Home"]
        else:
            display_row["Best Bet"] = "Pass"
        display_row["Bet Flag"] = bet_flag
        display_row["Park"] = round(matchup_results["park_factor"], 2)
        display_row["Weather"] = round(matchup_results["weather_multiplier"], 2)
        display_rows.append(display_row)

    return pd.DataFrame(display_rows, columns=TABLE_COLUMNS)


def get_market_edge_display(row):
    away_edge = row.get("Away Edge %")
    home_edge = row.get("Home Edge %")
    away_ev = row.get("Away EV")
    home_ev = row.get("Home EV")

    edge_candidates = []
    if away_edge is not None and not pd.isna(away_edge):
        edge_candidates.append(("Away", float(away_edge), away_ev))
    if home_edge is not None and not pd.isna(home_edge):
        edge_candidates.append(("Home", float(home_edge), home_ev))

    if not edge_candidates:
        return EDGE_PLACEHOLDER

    best_side, best_edge, best_ev = max(edge_candidates, key=lambda item: item[1])
    if best_ev is None or pd.isna(best_ev):
        return f"{best_side} {best_edge:.1f}% edge"
    return f"{best_side} {best_edge:.1f}% edge | {float(best_ev):.1f}% EV"


def format_probability_display(probability_value):
    """Format display-board probability values stored as percentages."""
    if probability_value is None or pd.isna(probability_value):
        return "N/A"
    return f"{float(probability_value):.1f}%"


def get_market_probability_pct(row, side_prefix):
    """
    Return the market win probability for a side as a percentage.

    The app prefers no-vig percentages when available because they are more
    comparable to the model probability. If those are missing, it falls back to
    the raw implied probability from the displayed moneyline.
    """
    no_vig_value = row.get(f"{side_prefix} No-Vig %")
    if no_vig_value is not None and not pd.isna(no_vig_value):
        return float(no_vig_value)

    implied_value = row.get(f"{side_prefix} Implied %")
    if implied_value is not None and not pd.isna(implied_value):
        return float(implied_value)

    return None


def get_model_fair_moneyline(probability_pct):
    """Convert a model win probability percentage into a fair American moneyline."""
    if probability_pct is None or pd.isna(probability_pct):
        return None
    return probability_to_american_odds(float(probability_pct) / 100.0)


def get_edge_tone(edge_value):
    """Map an edge percentage to the requested highlight color bands."""
    if edge_value is None or pd.isna(edge_value):
        return "pass"

    edge = float(edge_value)
    if edge > 3.0:
        return "strong"
    if edge >= 1.0:
        return "lean"
    if edge < -1.0:
        return "negative"
    return "pass"


def format_edge_badge(label, edge_value):
    """Render a color-coded edge badge for matchup-card summaries."""
    if edge_value is None or pd.isna(edge_value):
        return f'<span class="signal-badge pass">{label}: N/A</span>'

    tone = get_edge_tone(edge_value)
    return f'<span class="signal-badge {tone}">{label}: {float(edge_value):+.1f}%</span>'


def render_badge_row(primary_badge=None, bet_type_badge=None, favorite_badge=None):
    """
    Render a matchup-card badge row in one fixed left-to-right order.

    Order is always:
    1. primary recommendation badge
    2. bet-type label badge
    3. favorite badge, when applicable

    Any missing badge is omitted without changing the ordering of the remaining
    badges.
    """
    badges = []
    if primary_badge:
        badges.append(primary_badge)
    if bet_type_badge:
        badges.append(f'<span class="signal-badge label">{bet_type_badge}</span>')
    if favorite_badge:
        badges.append(f'<span class="favorite-badge">{favorite_badge}</span>')

    return f'<div class="chips-row">{"".join(badges)}</div>'


def format_side_angle_badge(best_side_label, favorite_team):
    """Highlight whether the current side angle is backing the favorite or the dog."""
    if best_side_label in {None, "Pass"} or pd.isna(best_side_label):
        return '<span class="angle-badge pass">No Side Angle</span>'
    if str(best_side_label) == str(favorite_team):
        return '<span class="angle-badge favorite">Favorite Value</span>'
    return '<span class="angle-badge underdog">Underdog Value</span>'


def format_total_angle_badge(best_total_bet_label):
    """Highlight whether the current total angle is on the over or under."""
    if best_total_bet_label in {None, "Pass"} or pd.isna(best_total_bet_label):
        return '<span class="angle-badge pass">No Total Angle</span>'
    if str(best_total_bet_label) == "Over":
        return '<span class="angle-badge over">Over Value</span>'
    if str(best_total_bet_label) == "Under":
        return '<span class="angle-badge under">Under Value</span>'
    return '<span class="angle-badge pass">No Total Angle</span>'


def build_total_edge_summary(row):
    """Return the most relevant total edge label and value for a matchup card."""
    over_edge = row.get("Over Edge %")
    under_edge = row.get("Under Edge %")
    best_total_bet = row.get("Best Total Bet")

    if best_total_bet == "Over" and over_edge is not None and not pd.isna(over_edge):
        return "Over", float(over_edge)
    if best_total_bet == "Under" and under_edge is not None and not pd.isna(under_edge):
        return "Under", float(under_edge)

    candidates = []
    if over_edge is not None and not pd.isna(over_edge):
        candidates.append(("Over", float(over_edge)))
    if under_edge is not None and not pd.isna(under_edge):
        candidates.append(("Under", float(under_edge)))

    if not candidates:
        return "Total Edge", None

    return max(candidates, key=lambda item: abs(item[1]))


def get_card_signal_style(row, best_side_edge, total_edge_value):
    """
    Choose a matchup-card stripe tone and badge label for quick scanning.

    Side opportunities take precedence when they are clearly actionable.
    Totals receive a distinct orange treatment when they are the strongest
    actionable angle on the card. Otherwise the card stays neutral or muted red
    if both available edges are clearly negative.
    """
    side_flag = row.get("Bet Flag")
    total_flag = row.get("Total Bet Flag")
    side_edge = float(best_side_edge) if best_side_edge is not None and not pd.isna(best_side_edge) else None
    total_edge = float(total_edge_value) if total_edge_value is not None and not pd.isna(total_edge_value) else None

    if side_flag == "Strong Bet" and side_edge is not None and side_edge > 3.0:
        return {"stripe": "strong", "badge_class": "top-side", "badge_text": "TOP SIDE"}
    if total_flag == "Strong Bet" and total_edge is not None and total_edge >= 2.0:
        return {"stripe": "total", "badge_class": "top-total", "badge_text": "TOP TOTAL"}
    if side_flag == "Lean" and side_edge is not None and side_edge >= 1.0:
        return {"stripe": "lean", "badge_class": "lean", "badge_text": "LEAN SIDE"}
    if total_flag == "Lean" and total_edge is not None and total_edge >= 1.0:
        return {"stripe": "total", "badge_class": "lean", "badge_text": "LEAN TOTAL"}

    negative_candidates = []
    if side_edge is not None:
        negative_candidates.append(side_edge)
    if total_edge is not None:
        negative_candidates.append(total_edge)
    if negative_candidates and max(negative_candidates) < -1.0:
        return {"stripe": "negative", "badge_class": "pass", "badge_text": "PASS"}

    return {"stripe": "pass", "badge_class": "pass", "badge_text": "PASS"}


def get_signal_tone(flag_value, ev_value=None):
    if ev_value is not None and not pd.isna(ev_value) and float(ev_value) < 0:
        return "negative"
    if flag_value == "Strong Bet":
        return "strong"
    if flag_value == "Lean":
        return "lean"
    return "pass"


def format_signal_badge(flag_value, ev_value=None):
    tone = get_signal_tone(flag_value, ev_value)
    label = "Negative EV" if tone == "negative" else (flag_value or "Pass")
    return f'<span class="signal-badge {tone}">{label}</span>'


def _flag_priority(flag_value):
    return {
        "Strong Bet": 2,
        "Lean": 1,
        "Pass": 0,
    }.get(flag_value, 0)


def _build_side_candidate(row):
    pick = row.get("Best Bet")
    flag_value = row.get("Bet Flag")
    if flag_value not in {"Lean", "Strong Bet"} or pick == "Pass" or pd.isna(pick):
        return None

    if pick == row.get("Away"):
        line_value = row.get("Away Moneyline")
        ev_value = row.get("Away EV")
        edge_value = row.get("Away Edge %")
    elif pick == row.get("Home"):
        line_value = row.get("Home Moneyline")
        ev_value = row.get("Home EV")
        edge_value = row.get("Home Edge %")
    else:
        return None

    if ev_value is None or pd.isna(ev_value):
        return None

    return {
        "matchup": f"{row['Away']} at {row['Home']}",
        "bet_type": "Side",
        "pick": pick,
        "sportsbook": row.get("Sportsbook") if pd.notna(row.get("Sportsbook")) else "N/A",
        "line": format_moneyline(line_value),
        "model_edge": float(edge_value) if edge_value is not None and not pd.isna(edge_value) else None,
        "ev": float(ev_value),
        "flag": flag_value,
        "projected_total": None,
        "market_total": None,
    }


def _build_total_candidate(row):
    pick = row.get("Best Total Bet")
    flag_value = row.get("Total Bet Flag")
    if flag_value not in {"Lean", "Strong Bet"} or pick == "Pass" or pd.isna(pick):
        return None

    if pick == "Over":
        line_value = row.get("Over Price")
        ev_value = row.get("Over EV")
        edge_value = row.get("Over Edge %")
    elif pick == "Under":
        line_value = row.get("Under Price")
        ev_value = row.get("Under EV")
        edge_value = row.get("Under Edge %")
    else:
        return None

    if ev_value is None or pd.isna(ev_value):
        return None

    market_total = row.get("Total Line")
    projected_total = row.get("Projected Total")
    line_label = f"{pick} {float(market_total):.1f}" if market_total is not None and not pd.isna(market_total) else pick

    return {
        "matchup": f"{row['Away']} at {row['Home']}",
        "bet_type": "Total",
        "pick": pick,
        "sportsbook": row.get("Sportsbook") if pd.notna(row.get("Sportsbook")) else "N/A",
        "line": f"{line_label} ({format_moneyline(line_value)})",
        "model_edge": float(edge_value) if edge_value is not None and not pd.isna(edge_value) else None,
        "ev": float(ev_value),
        "flag": flag_value,
        "projected_total": float(projected_total) if projected_total is not None and not pd.isna(projected_total) else None,
        "market_total": float(market_total) if market_total is not None and not pd.isna(market_total) else None,
    }


def build_top_plays_dataframe(display_df, max_plays=5):
    candidates = []

    for _, row in display_df.iterrows():
        side_candidate = _build_side_candidate(row)
        if side_candidate is not None:
            candidates.append(side_candidate)

        total_candidate = _build_total_candidate(row)
        if total_candidate is not None:
            candidates.append(total_candidate)

    if not candidates:
        return pd.DataFrame(
            columns=[
                "matchup",
                "bet_type",
                "pick",
                "sportsbook",
                "line",
                "model_edge",
                "ev",
                "flag",
                "projected_total",
                "market_total",
            ]
        )

    candidates_df = pd.DataFrame(candidates)
    candidates_df["flag_priority"] = candidates_df["flag"].map(_flag_priority)
    candidates_df["ev"] = pd.to_numeric(candidates_df["ev"], errors="coerce")
    candidates_df["model_edge"] = pd.to_numeric(candidates_df["model_edge"], errors="coerce")

    candidates_df = candidates_df.sort_values(
        by=["flag_priority", "ev", "model_edge"],
        ascending=[False, False, False],
        na_position="last",
    ).head(max_plays)

    return candidates_df.reset_index(drop=True)


def build_best_bets_summary(top_plays_df):
    if top_plays_df is None or top_plays_df.empty:
        return None, None

    top_side = top_plays_df[top_plays_df["bet_type"] == "Side"].copy()
    top_total = top_plays_df[top_plays_df["bet_type"] == "Total"].copy()
    if not top_side.empty:
        top_side = top_side.sort_values(by=["ev", "model_edge"], ascending=[False, False], na_position="last")
    if not top_total.empty:
        top_total = top_total.sort_values(by=["ev", "model_edge"], ascending=[False, False], na_position="last")

    side_row = top_side.iloc[0].to_dict() if not top_side.empty else None
    total_row = top_total.iloc[0].to_dict() if not top_total.empty else None
    return side_row, total_row


def build_summary_metrics(display_df):
    games_today = len(display_df)
    if games_today == 0:
        return {
            "games_today": 0,
            "avg_total_runs": "0.00",
            "strongest_ev": "No games loaded",
            "strongest_ev_delta": "",
            "playable_bets": 0,
            "playable_total_bets": 0,
        }

    avg_total_runs = (display_df["Away Runs"] + display_df["Home Runs"]).mean()
    betting_df = display_df[
        ["Away", "Home", "Away Edge %", "Home Edge %", "Away EV", "Home EV", "Best Bet", "Bet Flag"]
    ].copy()
    betting_df["Away Edge %"] = pd.to_numeric(betting_df["Away Edge %"], errors="coerce")
    betting_df["Home Edge %"] = pd.to_numeric(betting_df["Home Edge %"], errors="coerce")
    betting_df["Away EV"] = pd.to_numeric(betting_df["Away EV"], errors="coerce")
    betting_df["Home EV"] = pd.to_numeric(betting_df["Home EV"], errors="coerce")

    strongest_ev_text = "No positive EV spots"
    strongest_ev_delta = ""
    positive_away = betting_df["Away EV"].where(betting_df["Away EV"] > 0)
    positive_home = betting_df["Home EV"].where(betting_df["Home EV"] > 0)

    if not pd.isna(positive_away).all() or not pd.isna(positive_home).all():
        away_best_idx = positive_away.idxmax() if not pd.isna(positive_away).all() else None
        home_best_idx = positive_home.idxmax() if not pd.isna(positive_home).all() else None
        away_best_ev = positive_away.loc[away_best_idx] if away_best_idx is not None else None
        home_best_ev = positive_home.loc[home_best_idx] if home_best_idx is not None else None

        if away_best_ev is not None and not pd.isna(away_best_ev) and (
            home_best_ev is None or pd.isna(home_best_ev) or away_best_ev >= home_best_ev
        ):
            strongest_ev_text = f"{betting_df.loc[away_best_idx, 'Away']} away"
            strongest_ev_delta = f"{away_best_ev:.1f}% EV"
        elif home_best_ev is not None and not pd.isna(home_best_ev):
            strongest_ev_text = f"{betting_df.loc[home_best_idx, 'Home']} home"
            strongest_ev_delta = f"{home_best_ev:.1f}% EV"

    playable_bets = int(display_df["Bet Flag"].isin(["Lean", "Strong Bet"]).sum())
    playable_total_bets = int(display_df["Total Bet Flag"].isin(["Lean", "Strong Bet"]).sum())

    return {
        "games_today": games_today,
        "avg_total_runs": f"{avg_total_runs:.2f}",
        "strongest_ev": strongest_ev_text,
        "strongest_ev_delta": strongest_ev_delta,
        "playable_bets": playable_bets,
        "playable_total_bets": playable_total_bets,
    }


def _build_top_play_strip_item(label, tone, title, edge_text, supporting_text):
    """Create one compact top-strip card payload."""
    return {
        "label": label,
        "tone": tone,
        "title": title,
        "edge_text": edge_text,
        "supporting_text": supporting_text,
    }


def build_top_plays_today_items(display_df, top_plays_df):
    """
    Build the short list of high-signal plays for the top dashboard strip.

    Actual playable edges are prioritized. If the current board has no positive
    EV opportunities, the strip falls back to a clean pass summary plus the
    strongest model favorite.
    """
    items = []
    side_df = pd.DataFrame()
    total_df = pd.DataFrame()

    if top_plays_df is not None and not top_plays_df.empty:
        side_df = top_plays_df[top_plays_df["bet_type"] == "Side"].copy()
        total_df = top_plays_df[top_plays_df["bet_type"] == "Total"].copy()

    if not side_df.empty:
        side_df = side_df.sort_values(by=["ev", "model_edge"], ascending=[False, False], na_position="last")
        best_side = side_df.iloc[0]
        side_tone = "lean" if best_side["flag"] == "Lean" else "side"
        side_label = "LEAN" if best_side["flag"] == "Lean" else "SIDE"
        items.append(
            _build_top_play_strip_item(
                label=side_label,
                tone=side_tone,
                title=f"{best_side['pick']} {best_side['line']}",
                edge_text=f"{float(best_side['model_edge']):+.1f}% edge" if pd.notna(best_side["model_edge"]) else "Edge N/A",
                supporting_text=f"{best_side['matchup']} | Favorite/side angle",
            )
        )

        if len(side_df) > 1:
            second_side = side_df.iloc[1]
            second_tone = "lean" if second_side["flag"] == "Lean" else "side"
            second_label = "LEAN" if second_side["flag"] == "Lean" else "SIDE"
            items.append(
                _build_top_play_strip_item(
                    label=second_label,
                    tone=second_tone,
                    title=f"{second_side['pick']} {second_side['line']}",
                    edge_text=f"{float(second_side['model_edge']):+.1f}% edge" if pd.notna(second_side["model_edge"]) else "Edge N/A",
                    supporting_text=f"{second_side['matchup']} | Secondary side",
                )
            )

    if not total_df.empty:
        total_df = total_df.sort_values(by=["ev", "model_edge"], ascending=[False, False], na_position="last")
        best_total = total_df.iloc[0]
        total_tone = "lean" if best_total["flag"] == "Lean" else "total"
        total_label = "LEAN" if best_total["flag"] == "Lean" else "TOTAL"
        items.append(
            _build_top_play_strip_item(
                label=total_label,
                tone=total_tone,
                title=f"{best_total['pick']} {best_total['line']}",
                edge_text=f"{float(best_total['model_edge']):+.1f}% edge" if pd.notna(best_total["model_edge"]) else "Edge N/A",
                supporting_text=f"{best_total['matchup']} | {best_total['pick']}",
            )
        )

    if items:
        return items[:3]

    if display_df.empty:
        return [
            _build_top_play_strip_item(
                label="PASS",
                tone="pass",
                title="No games loaded",
                edge_text="No board data",
                supporting_text="Add or refresh the current slate to generate plays.",
            )
        ]

    strongest_favorite_row = display_df.loc[display_df["Win Edge"].astype(float).idxmax()]
    strongest_favorite_team = strongest_favorite_row["Favorite"]
    strongest_favorite_prob = max(float(strongest_favorite_row["Away Win"]), float(strongest_favorite_row["Home Win"]))

    return [
        _build_top_play_strip_item(
            label="PASS",
            tone="pass",
            title="No positive EV plays on the board",
            edge_text="Pass for now",
            supporting_text="Current prices do not create a playable side or total edge.",
        ),
        _build_top_play_strip_item(
            label="PASS",
            tone="pass",
            title=f"Strongest model favorite: {strongest_favorite_team}",
            edge_text=f"{strongest_favorite_prob:.1f}% win probability",
            supporting_text=f"{strongest_favorite_row['Away']} at {strongest_favorite_row['Home']}",
        ),
    ]


def get_board_row_scores(row):
    side_edges = [
        float(value)
        for value in [row.get("Away Edge %"), row.get("Home Edge %")]
        if value is not None and not pd.isna(value)
    ]
    total_edges = [
        float(value)
        for value in [row.get("Over Edge %"), row.get("Under Edge %")]
        if value is not None and not pd.isna(value)
    ]
    side_evs = [
        float(value)
        for value in [row.get("Away EV"), row.get("Home EV")]
        if value is not None and not pd.isna(value)
    ]
    total_evs = [
        float(value)
        for value in [row.get("Over EV"), row.get("Under EV")]
        if value is not None and not pd.isna(value)
    ]
    return {
        "best_side_edge": max(side_edges) if side_edges else None,
        "best_total_edge": max(total_edges) if total_edges else None,
        "best_side_ev": max(side_evs) if side_evs else None,
        "best_total_ev": max(total_evs) if total_evs else None,
        "best_any_ev": max(side_evs + total_evs) if (side_evs or total_evs) else None,
        "closest_game_margin": abs(float(row.get("Away Win", 0.0)) - float(row.get("Home Win", 0.0))),
        "favorite_win_prob": max(float(row.get("Away Win", 0.0)), float(row.get("Home Win", 0.0))),
    }


def render_board_view_controls(display_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Board View</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Filter, sort, and switch views so the slate reads like a decision board instead of a raw schedule.</div>',
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([1.2, 0.8])
    with left_col:
        st.markdown('<div class="board-view-card">', unsafe_allow_html=True)
        control_col_1, control_col_2 = st.columns(2)
        with control_col_1:
            signal_filter = st.selectbox(
                "Signal",
                ["All Games", "Strong Bets", "Leans", "Playable Only", "Passes Only"],
                key="board_signal_filter",
            )
        with control_col_2:
            angle_filter = st.selectbox(
                "Angle",
                ["All Angles", "Side Angles", "Total Angles", "Favorite Sides", "Underdog Sides"],
                key="board_angle_filter",
            )
        control_col_3, control_col_4 = st.columns(2)
        with control_col_3:
            sort_option = st.selectbox(
                "Sort",
                [
                    "Schedule Order",
                    "Highest EV",
                    "Biggest Side Edge",
                    "Biggest Total Edge",
                    "Highest Win Probability",
                    "Closest Game",
                ],
                key="board_sort_option",
            )
        with control_col_4:
            view_mode = st.radio(
                "View",
                ["Cards", "Table"],
                key="board_view_mode",
                horizontal=True,
            )

        filter_col_1, filter_col_2 = st.columns(2)
        with filter_col_1:
            side_value_filter = st.selectbox(
                "Side Value",
                ["All Side Angles", "Favorite Value", "Underdog Value", "No Side Angle"],
                key="board_side_value_filter",
            )
        with filter_col_2:
            total_value_filter = st.selectbox(
                "Total Value",
                ["All Total Angles", "Over Value", "Under Value", "No Total Angle"],
                key="board_total_value_filter",
            )
        sportsbook_col, _ = st.columns([1.2, 0.8])
        with sportsbook_col:
            sportsbook_options = ["All Sportsbooks"] + sorted(
                {
                    str(book)
                    for book in display_df.get("Sportsbook", pd.Series(dtype="object")).dropna().tolist()
                    if str(book).strip()
                }
            )
            sportsbook_filter = st.selectbox(
                "Sportsbook",
                sportsbook_options,
                key="board_sportsbook_filter",
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with right_col:
        st.markdown('<div class="board-view-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-section-label">Data Freshness</div>', unsafe_allow_html=True)
        freshness_pills = [
            ("Board Inputs", format_board_timestamp("board_inputs_last_updated")),
            ("Odds", format_board_timestamp("odds_last_updated")),
            ("Simulations", format_board_timestamp("simulation_last_updated")),
        ]
        freshness_html = "".join(
            f'<span class="freshness-pill">{label}: {timestamp_text}</span>'
            for label, timestamp_text in freshness_pills
        )
        st.markdown(f'<div class="freshness-pills">{freshness_html}</div>', unsafe_allow_html=True)
        st.caption("Freshness updates when the board reloads, odds refresh, or simulations are explicitly rerun.")
        st.markdown('</div>', unsafe_allow_html=True)

    filtered_df = display_df.copy()

    if signal_filter == "Strong Bets":
        filtered_df = filtered_df.loc[
            (filtered_df["Bet Flag"] == "Strong Bet") | (filtered_df["Total Bet Flag"] == "Strong Bet")
        ]
    elif signal_filter == "Leans":
        filtered_df = filtered_df.loc[
            (filtered_df["Bet Flag"] == "Lean") | (filtered_df["Total Bet Flag"] == "Lean")
        ]
    elif signal_filter == "Playable Only":
        filtered_df = filtered_df.loc[
            filtered_df["Bet Flag"].isin(["Lean", "Strong Bet"])
            | filtered_df["Total Bet Flag"].isin(["Lean", "Strong Bet"])
        ]
    elif signal_filter == "Passes Only":
        filtered_df = filtered_df.loc[
            (filtered_df["Bet Flag"] == "Pass") & (filtered_df["Total Bet Flag"] == "Pass")
        ]

    if angle_filter == "Side Angles":
        filtered_df = filtered_df.loc[filtered_df["Best Bet"] != "Pass"]
    elif angle_filter == "Total Angles":
        filtered_df = filtered_df.loc[filtered_df["Best Total Bet"] != "Pass"]
    elif angle_filter == "Favorite Sides":
        filtered_df = filtered_df.loc[
            (filtered_df["Best Bet"] != "Pass") & (filtered_df["Best Bet"] == filtered_df["Favorite"])
        ]
    elif angle_filter == "Underdog Sides":
        filtered_df = filtered_df.loc[
            (filtered_df["Best Bet"] != "Pass") & (filtered_df["Best Bet"] != filtered_df["Favorite"])
        ]

    if side_value_filter == "Favorite Value":
        filtered_df = filtered_df.loc[
            (filtered_df["Best Bet"] != "Pass") & (filtered_df["Best Bet"] == filtered_df["Favorite"])
        ]
    elif side_value_filter == "Underdog Value":
        filtered_df = filtered_df.loc[
            (filtered_df["Best Bet"] != "Pass") & (filtered_df["Best Bet"] != filtered_df["Favorite"])
        ]
    elif side_value_filter == "No Side Angle":
        filtered_df = filtered_df.loc[filtered_df["Best Bet"] == "Pass"]

    if total_value_filter == "Over Value":
        filtered_df = filtered_df.loc[filtered_df["Best Total Bet"] == "Over"]
    elif total_value_filter == "Under Value":
        filtered_df = filtered_df.loc[filtered_df["Best Total Bet"] == "Under"]
    elif total_value_filter == "No Total Angle":
        filtered_df = filtered_df.loc[filtered_df["Best Total Bet"] == "Pass"]

    if sportsbook_filter != "All Sportsbooks":
        filtered_df = filtered_df.loc[filtered_df["Sportsbook"] == sportsbook_filter]

    if not filtered_df.empty:
        filtered_df = filtered_df.copy()
        row_scores = filtered_df.apply(get_board_row_scores, axis=1, result_type="expand")
        filtered_df = pd.concat([filtered_df, row_scores], axis=1)

        if sort_option == "Highest EV":
            filtered_df = filtered_df.sort_values(by="best_any_ev", ascending=False, na_position="last")
        elif sort_option == "Biggest Side Edge":
            filtered_df = filtered_df.sort_values(by="best_side_edge", ascending=False, na_position="last")
        elif sort_option == "Biggest Total Edge":
            filtered_df = filtered_df.sort_values(by="best_total_edge", ascending=False, na_position="last")
        elif sort_option == "Highest Win Probability":
            filtered_df = filtered_df.sort_values(by="favorite_win_prob", ascending=False, na_position="last")
        elif sort_option == "Closest Game":
            filtered_df = filtered_df.sort_values(by="closest_game_margin", ascending=True, na_position="last")

        filtered_df = filtered_df.drop(
            columns=[
                "best_side_edge",
                "best_total_edge",
                "best_side_ev",
                "best_total_ev",
                "best_any_ev",
                "closest_game_margin",
                "favorite_win_prob",
            ],
            errors="ignore",
        )

    filtered_count = len(filtered_df)
    source_count = len(display_df)
    st.caption(
        f"Showing {filtered_count} of {source_count} games | Signal: {signal_filter} | Angle: {angle_filter} | Side: {side_value_filter} | Total: {total_value_filter} | Sort: {sort_option}"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    return filtered_df, view_mode


def render_board_empty_state(source_df, filtered_df):
    st.markdown('<div class="board-empty-card">', unsafe_allow_html=True)
    if filtered_df.empty and not source_df.empty:
        title = "No games match the current board filters"
        copy = "Try widening the signal, angle, or sportsbook filters. The underlying slate is still loaded and ready."
    else:
        title = "No positive EV positions on the current board"
        copy = "The model still has opinions, but current prices are not creating a playable edge right now."

    strongest_favorite_text = "N/A"
    near_miss_text = "N/A"
    totals_text = "N/A"
    if not source_df.empty:
        strongest_row = source_df.loc[source_df["Win Edge"].astype(float).idxmax()]
        strongest_team = strongest_row["Favorite"]
        strongest_prob = max(float(strongest_row["Away Win"]), float(strongest_row["Home Win"]))
        strongest_favorite_text = f"{strongest_team} {strongest_prob:.1f}%"

        near_miss_candidates = []
        for _, row in source_df.iterrows():
            scores = get_board_row_scores(row)
            best_ev = scores["best_any_ev"]
            if best_ev is not None:
                near_miss_candidates.append((best_ev, f"{row['Away']} at {row['Home']}"))
        if near_miss_candidates:
            near_miss_ev, near_miss_game = max(near_miss_candidates, key=lambda item: item[0])
            near_miss_text = f"{near_miss_game} | {near_miss_ev:+.1f}% EV"

        playable_total_count = int(source_df["Total Bet Flag"].isin(["Lean", "Strong Bet"]).sum())
        totals_text = f"{playable_total_count} playable totals"

    st.markdown(f'<div class="board-empty-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="board-empty-copy">{copy}</div>', unsafe_allow_html=True)
    st.markdown(
        dedent(
            f"""
            <div class="board-empty-grid">
                <div class="board-empty-metric">
                    <div class="board-empty-label">Strongest Favorite</div>
                    <div class="board-empty-value">{strongest_favorite_text}</div>
                </div>
                <div class="board-empty-metric">
                    <div class="board-empty-label">Closest To Playable</div>
                    <div class="board-empty-value">{near_miss_text}</div>
                </div>
                <div class="board-empty-metric">
                    <div class="board-empty-label">Total Board Pulse</div>
                    <div class="board-empty-value">{totals_text}</div>
                </div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)


def render_matchup_table(display_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Matchup Board</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Compact comparison view for scanning the whole slate side by side.</div>',
        unsafe_allow_html=True,
    )
    if display_df.empty:
        st.info("No games loaded for the current board.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    compact_df = display_df[
        [
            "Away",
            "Home",
            "Favorite",
            "Away Win",
            "Home Win",
            "Best Bet",
            "Bet Flag",
            "Away Edge %",
            "Home Edge %",
            "Best Total Bet",
            "Total Bet Flag",
            "Projected Total",
            "Total Diff",
            "Sportsbook",
        ]
    ].copy()
    st.dataframe(
        compact_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Away Win": st.column_config.NumberColumn("Away Win", format="%.1f%%"),
            "Home Win": st.column_config.NumberColumn("Home Win", format="%.1f%%"),
            "Away Edge %": st.column_config.NumberColumn("Away Edge", format="%.1f%%"),
            "Home Edge %": st.column_config.NumberColumn("Home Edge", format="%.1f%%"),
            "Projected Total": st.column_config.NumberColumn("Proj Total", format="%.2f"),
            "Total Diff": st.column_config.NumberColumn("Total Diff", format="%.2f"),
        },
    )
    st.markdown('</div>', unsafe_allow_html=True)


def render_daily_board_drawer(display_df, download_csv, run_dispersion):
    with st.expander("Board Filter", expanded=False):
        top_plays_df = render_top_plays(display_df)
        render_summary_metrics(display_df)
        render_top_plays_today(display_df, top_plays_df)
        render_action_bar(download_csv, display_df, top_plays_df, run_dispersion)
        filtered_display_df, board_view_mode = render_board_view_controls(display_df)
    return top_plays_df, filtered_display_df, board_view_mode


def render_controls_panel():
    with st.expander("Controls", expanded=False):
        st.markdown('<div class="section-panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Controls</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-subtitle">Configure live odds and simulation settings before scanning the current board.</div>',
            unsafe_allow_html=True,
        )
        control_col_1, control_col_2 = st.columns(2)
        with control_col_1:
            st.markdown('<div class="control-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-label">Odds Feed</div>', unsafe_allow_html=True)
            render_odds_config()
            st.markdown('</div>', unsafe_allow_html=True)
        with control_col_2:
            st.markdown('<div class="control-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-label">Simulation</div>', unsafe_allow_html=True)
            render_simulation_config()
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_summary_metrics(display_df):
    st.markdown('<div class="sticky-summary-shell"><div class="section-panel">', unsafe_allow_html=True)
    summary = build_summary_metrics(display_df)
    metric_row_1_col_1, metric_row_1_col_2 = st.columns(2)
    with metric_row_1_col_1:
        st.metric("Games Today", summary["games_today"])
    with metric_row_1_col_2:
        st.metric("Strongest EV", summary["strongest_ev"], summary["strongest_ev_delta"])
    metric_row_2_col_1, metric_row_2_col_2 = st.columns(2)
    with metric_row_2_col_1:
        st.metric("Playable Side Bets", summary["playable_bets"])
    with metric_row_2_col_2:
        st.metric("Playable Total Bets", summary["playable_total_bets"])
    st.markdown('</div></div>', unsafe_allow_html=True)


def render_top_plays_today(display_df, top_plays_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Top Plays Today</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Fast-read strip for the strongest current board signals before you scan the full matchup cards.</div>',
        unsafe_allow_html=True,
    )

    top_strip_items = build_top_plays_today_items(display_df, top_plays_df)
    for start_idx in range(0, len(top_strip_items), 2):
        row_items = top_strip_items[start_idx:start_idx + 2]
        strip_columns = st.columns(len(row_items))
        for column, item in zip(strip_columns, row_items):
            with column:
                st.markdown(
                    dedent(
                        f"""
                        <div class="top-strip-card {item['tone']}">
                            <div class="top-strip-label {item['tone']}">{item['label']}</div>
                            <div class="top-strip-title">{item['title']}</div>
                            <div class="top-strip-edge">{item['edge_text']}</div>
                            <div class="top-strip-meta">{item['supporting_text']}</div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )

    st.markdown('</div>', unsafe_allow_html=True)


def render_top_plays(display_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Best Bets</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Top side and total opportunities ranked by signal strength, EV, and model edge.</div>',
        unsafe_allow_html=True,
    )

    top_plays_df = build_top_plays_dataframe(display_df)
    if top_plays_df.empty:
        st.info("No playable bets on the board right now.")
        st.markdown('</div>', unsafe_allow_html=True)
        return top_plays_df

    best_side, best_total = build_best_bets_summary(top_plays_df)
    spotlight_cards = ['<div class="best-bets-grid">']
    for card_title, row in [("Best Side", best_side), ("Best Total", best_total)]:
        if row is None:
            spotlight_cards.append(
                dedent(
                    f"""
                    <div class="best-bet-card">
                        <div class="top-play-rank">{card_title}</div>
                        <div class="top-play-pick">No current play</div>
                        <div class="top-play-meta">Waiting for a qualifying {card_title.lower()} signal.</div>
                    </div>
                    """
                ).strip()
            )
            continue

        spotlight_cards.append(
            dedent(
                f"""
                <div class="best-bet-card">
                    <div class="top-play-rank">{card_title}</div>
                    <div class="top-play-pick">{row['pick']} {row['line']}</div>
                    <div class="top-play-meta">{row['matchup']} | {row['sportsbook']}</div>
                    <div class="top-play-stats">EV: {row['ev']:+.1f}% | Edge: {row['model_edge']:+.1f}%</div>
                    <div class="top-play-meta">{format_signal_badge(row['flag'], row['ev'])}</div>
                </div>
                """
            ).strip()
        )

    spotlight_cards.append("</div>")
    st.markdown("".join(spotlight_cards), unsafe_allow_html=True)

    st.download_button(
        label="Download Top Plays CSV",
        data=top_plays_df.to_csv(index=False),
        file_name="top_plays.csv",
        mime="text/csv",
    )

    cards_html = ['<div class="top-plays-grid">']
    for rank, (_, row) in enumerate(top_plays_df.iterrows(), start=1):
        tone = get_signal_tone(row["flag"], row["ev"])
        card_class = f"top-play-card {tone}"
        matchup_copy = row["matchup"]
        meta_copy = f"{row['bet_type']} | {row['sportsbook']}"
        stats_copy = f"EV: {row['ev']:+.1f}%"
        if row["model_edge"] is not None and not pd.isna(row["model_edge"]):
            stats_copy += f" | Edge: {row['model_edge']:+.1f}%"

        detail_copy = matchup_copy
        if row["bet_type"] == "Total":
            market_total = row.get("market_total")
            projected_total = row.get("projected_total")
            if market_total is not None and projected_total is not None:
                detail_copy = (
                    f"{matchup_copy} | Total {float(market_total):.1f} | "
                    f"Projected {float(projected_total):.2f}"
                )

        cards_html.append(
            dedent(
                f"""
                <div class="{card_class}">
                    <div class="top-play-rank">#{rank} {row["flag"]}</div>
                    <div class="top-play-pick">{row["pick"]} {row["line"]}</div>
                    <div class="top-play-meta">{meta_copy}</div>
                    <div class="top-play-stats">{stats_copy}</div>
                    <div class="top-play-matchup">{detail_copy}</div>
                </div>
                """
            ).strip()
        )

    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    return top_plays_df


def render_action_bar(download_csv, display_df, top_plays_df, run_dispersion):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Board Controls</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Refresh pricing, save snapshots, and export the current slate without affecting model logic.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="toolbar-shell">', unsafe_allow_html=True)
    st.markdown(
        '<div class="toolbar-note">Board inputs stay editable while projections, favorite flags, and exported results remain synced to the latest simulation output.</div>',
        unsafe_allow_html=True,
    )

    action_row_1_col_1, action_row_1_col_2, action_row_1_col_3 = st.columns(3)
    with action_row_1_col_1:
        if st.button("Refresh Board", use_container_width=True):
            reload_automated_inputs(force_refresh=True)
            st.rerun()
    with action_row_1_col_2:
        if st.button("Refresh Simulations", use_container_width=True):
            st.cache_data.clear()
            set_board_timestamp("simulation_last_updated")
            st.session_state["simulation_cache_status"] = (
                "success",
                "Simulation cache cleared. Matchups will recompute on the next render.",
            )
            st.rerun()
    with action_row_1_col_3:
        if st.button("Load Live Odds", use_container_width=True):
            try:
                odds_map = fetch_live_odds()
                updated_board, matched_games = apply_live_odds_to_board(
                    st.session_state["daily_board_inputs"],
                    odds_map,
                )
                st.session_state["daily_board_inputs"] = updated_board
                st.session_state["live_odds_market_data"] = odds_map
                set_board_timestamp("odds_last_updated")
                if matched_games > 0:
                    st.session_state["odds_status"] = (
                        "success",
                        f"Loaded live odds for {matched_games} matchup(s).",
                    )
                else:
                    st.session_state["odds_status"] = (
                        "warning",
                        "No live odds matched the current board.",
                    )
                st.rerun()
            except Exception as exc:
                st.session_state["odds_status"] = ("error", f"Live odds load failed: {exc}")
                st.rerun()

    action_row_2_col_1, action_row_2_col_2 = st.columns(2)
    with action_row_2_col_1:
        if st.button("Save Board Snapshot", use_container_width=True):
            try:
                board_snapshot_path = save_board_snapshot(display_df, run_dispersion)
                top_plays_snapshot_path = save_top_plays_snapshot(top_plays_df, run_dispersion)
                snapshot_message = f"Saved board snapshot to {os.path.basename(board_snapshot_path)}."
                if top_plays_snapshot_path:
                    snapshot_message += f" Top plays saved to {os.path.basename(top_plays_snapshot_path)}."
                st.session_state["snapshot_status"] = ("success", snapshot_message)
            except Exception as exc:
                st.session_state["snapshot_status"] = ("error", f"Snapshot save failed: {exc}")
            st.rerun()
    with action_row_2_col_2:
        st.download_button(
            label="Download CSV",
            data=download_csv,
            file_name="daily_matchup_simulations.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    odds_status = st.session_state.get("odds_status")
    if odds_status:
        status_level, status_message = odds_status
        if status_level == "success":
            st.success(status_message)
        elif status_level == "warning":
            st.warning(status_message)
        else:
            st.error(status_message)

    simulation_cache_status = st.session_state.get("simulation_cache_status")
    if simulation_cache_status:
        status_level, status_message = simulation_cache_status
        if status_level == "success":
            st.success(status_message)
        elif status_level == "warning":
            st.warning(status_message)
        else:
            st.error(status_message)
        st.session_state.pop("simulation_cache_status", None)

    snapshot_status = st.session_state.get("snapshot_status")
    if snapshot_status:
        status_level, status_message = snapshot_status
        if status_level == "success":
            st.success(status_message)
        elif status_level == "warning":
            st.warning(status_message)
        else:
            st.error(status_message)
        st.session_state.pop("snapshot_status", None)

    st.markdown("</div>", unsafe_allow_html=True)


def render_matchup_cards(display_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Matchup Board</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Quick-scan cards with the best side and total angles up front, plus deeper market context on demand.</div>',
        unsafe_allow_html=True,
    )

    if display_df.empty:
        st.info("No games loaded for the current board.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    preview_columns = st.columns(2)

    for idx, (_, row) in enumerate(display_df.iterrows()):
        favorite_is_home = row["Favorite"] == row["Home"]
        favorite_team = row["Home"] if favorite_is_home else row["Away"]
        favorite_prob = row["Home Win"] if favorite_is_home else row["Away Win"]

        side_ev_candidates = [
            value for value in [row.get("Away EV"), row.get("Home EV")]
            if value is not None and not pd.isna(value)
        ]
        best_side_ev = max(side_ev_candidates) if side_ev_candidates else None
        tone = get_signal_tone(row.get("Bet Flag"), best_side_ev)
        card_class = f"board-card {tone}-side"
        if row["Win Edge"] >= 8:
            card_class += " favorite-card"

        away_moneyline = format_moneyline(row.get("Away Moneyline"))
        home_moneyline = format_moneyline(row.get("Home Moneyline"))
        sportsbook_name = row.get("Sportsbook") if pd.notna(row.get("Sportsbook")) else "N/A"
        away_market_prob = get_market_probability_pct(row, "Away")
        home_market_prob = get_market_probability_pct(row, "Home")
        away_fair_moneyline = format_moneyline(get_model_fair_moneyline(row.get("Away Win")))
        home_fair_moneyline = format_moneyline(get_model_fair_moneyline(row.get("Home Win")))
        away_edge_value = row.get("Away Edge %")
        home_edge_value = row.get("Home Edge %")
        total_edge_label, total_edge_value = build_total_edge_summary(row)
        side_edge_candidates = [
            value for value in [away_edge_value, home_edge_value]
            if value is not None and not pd.isna(value)
        ]
        best_side_edge = max(side_edge_candidates) if side_edge_candidates else None
        card_signal = get_card_signal_style(row, best_side_edge=best_side_edge, total_edge_value=total_edge_value)

        away_consensus_value = row.get("Away Consensus %")
        home_consensus_value = row.get("Home Consensus %")
        if pd.notna(away_consensus_value) and pd.notna(home_consensus_value):
            consensus_probability_label = f"{float(away_consensus_value):.1f}% / {float(home_consensus_value):.1f}%"
        else:
            consensus_probability_label = "N/A"

        best_side_label = row["Best Bet"] if row["Best Bet"] != "Pass" else "Pass"
        best_total_bet_label = row["Best Total Bet"] if row["Best Total Bet"] != "Pass" else "Pass"

        away_ev_value = row.get("Away EV")
        home_ev_value = row.get("Home EV")
        over_edge_value = row.get("Over Edge %")
        under_edge_value = row.get("Under Edge %")
        over_ev_value = row.get("Over EV")
        under_ev_value = row.get("Under EV")
        total_diff_value = row.get("Total Diff")

        if best_side_label == row["Away"]:
            if pd.notna(away_edge_value) and pd.notna(away_ev_value):
                best_side_summary = f"Away {float(away_edge_value):.1f}% edge | {float(away_ev_value):.1f}% EV"
            else:
                best_side_summary = "N/A"
        elif best_side_label == row["Home"]:
            if pd.notna(home_edge_value) and pd.notna(home_ev_value):
                best_side_summary = f"Home {float(home_edge_value):.1f}% edge | {float(home_ev_value):.1f}% EV"
            else:
                best_side_summary = "N/A"
        else:
            best_side_summary = "No playable edge"

        if best_total_bet_label == "Over":
            if pd.notna(over_edge_value) and pd.notna(over_ev_value):
                total_bet_summary = f"Over {float(over_edge_value):.1f}% edge | {float(over_ev_value):.1f}% EV"
            else:
                total_bet_summary = "N/A"
        elif best_total_bet_label == "Under":
            if pd.notna(under_edge_value) and pd.notna(under_ev_value):
                total_bet_summary = f"Under {float(under_edge_value):.1f}% edge | {float(under_ev_value):.1f}% EV"
            else:
                total_bet_summary = "N/A"
        else:
            total_bet_summary = "No playable total"

        side_badges = render_badge_row(
            primary_badge=format_signal_badge(row["Bet Flag"], best_side_ev),
            bet_type_badge="Best Bet",
            favorite_badge=f"Favorite: {favorite_team} {favorite_prob:.1f}%",
        )
        side_angle_badge = format_side_angle_badge(best_side_label, favorite_team)
        total_angle_badge = format_total_angle_badge(best_total_bet_label)

        total_ev_candidates = [
            value for value in [row.get("Over EV"), row.get("Under EV")]
            if value is not None and not pd.isna(value)
        ]
        best_total_ev = max(total_ev_candidates) if total_ev_candidates else None

        total_badges = render_badge_row(
            primary_badge=format_signal_badge(row["Total Bet Flag"], best_total_ev),
            bet_type_badge="Best Total",
        )

        with preview_columns[idx % 2]:
            with st.container(border=True):
                st.markdown(
                    dedent(
                        f"""
                        <div class="board-card-shell">
                            <div class="board-card-stripe {card_signal['stripe']}"></div>
                            <div class="{card_class}">
                                <div class="board-topline">
                                    <div>
                                        <div class="board-matchup">{row["Away"]} at {row["Home"]}</div>
                                        <div class="board-subtle">{row["Away Pitcher"]} vs {row["Home Pitcher"]}</div>
                                    </div>
                                    <div class="board-status-badge {card_signal['badge_class']}">{card_signal['badge_text']}</div>
                                </div>
                                <div class="board-status-row">
                                    <div class="board-subtle">{sportsbook_name}</div>
                                    {side_angle_badge}
                                    {total_angle_badge}
                                </div>
                            </div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    dedent(
                        f"""
                        <div class="score-ribbon">
                            <div class="score-ribbon-label">Projected Score</div>
                            <div class="score-ribbon-value">{row["Away"]} {row["Away Runs"]:.2f} - {row["Home"]} {row["Home Runs"]:.2f}</div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )

                st.markdown(
                    dedent(
                        f"""
                        <div class="bet-slip-grid">
                            <div class="bet-slip-card side">
                                <div class="bet-slip-label">Best Side Bet</div>
                                <div class="bet-slip-pick">{best_side_label}</div>
                                {side_badges}
                                <div class="bet-slip-summary">{best_side_summary}</div>
                            </div>
                            <div class="bet-slip-card total">
                                <div class="bet-slip-label">Best Total Bet</div>
                                <div class="bet-slip-pick">{best_total_bet_label}</div>
                                {total_badges}
                                <div class="bet-slip-summary">{total_bet_summary}</div>
                            </div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )

                st.markdown('<div class="card-section-divider"></div>', unsafe_allow_html=True)
                st.markdown('<div class="card-section-label">Model Probabilities</div>', unsafe_allow_html=True)
                away_win_prob = float(row.get("Away Win", 0.0))
                home_win_prob = float(row.get("Home Win", 0.0))
                away_bar_class = "favorite" if favorite_team == row["Away"] else "underdog"
                home_bar_class = "favorite" if favorite_team == row["Home"] else "underdog"
                st.markdown(
                    dedent(
                        f"""
                        <div class="probability-line">
                            <div class="probability-team">{row["Away"]}</div>
                            <div class="probability-value">{away_win_prob:.1f}%</div>
                            <div class="probability-bar-track">
                                <div class="probability-bar-fill {away_bar_class}" style="width: {away_win_prob}%;"></div>
                            </div>
                        </div>
                        <div class="probability-line">
                            <div class="probability-team">{row["Home"]}</div>
                            <div class="probability-value">{home_win_prob:.1f}%</div>
                            <div class="probability-bar-track">
                                <div class="probability-bar-fill {home_bar_class}" style="width: {home_win_prob}%;"></div>
                            </div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )

                st.markdown('<div class="card-section-divider"></div>', unsafe_allow_html=True)
                st.markdown('<div class="card-section-label">Totals</div>', unsafe_allow_html=True)
                total_col_1, total_col_2, total_col_3 = st.columns(3)
                with total_col_1:
                    st.metric("Projected Total", f"{float(row['Projected Total']):.2f}")
                with total_col_2:
                    market_total_display = (
                        f"{float(row['Total Line']):.1f}" if pd.notna(row.get("Total Line")) else "N/A"
                    )
                    st.metric("Market Total", market_total_display)
                with total_col_3:
                    total_edge_display = (
                        f"{total_edge_label} {float(total_edge_value):+.1f}%"
                        if total_edge_value is not None and not pd.isna(total_edge_value)
                        else "N/A"
                    )
                    st.metric("Total Edge", total_edge_display)
                    st.markdown(format_edge_badge(total_edge_label, total_edge_value), unsafe_allow_html=True)

                with st.expander("Market detail", expanded=False):
                    st.markdown('<div class="card-section-label">Sides Market</div>', unsafe_allow_html=True)
                    market_col_1, market_col_2 = st.columns(2)
                    with market_col_1:
                        st.metric("Market ML", away_moneyline)
                        st.metric("Market Win", format_probability_display(away_market_prob))
                        st.metric("Fair ML", away_fair_moneyline)
                        st.markdown(format_edge_badge(f"{row['Away']} Edge", away_edge_value), unsafe_allow_html=True)
                    with market_col_2:
                        st.metric("Market ML", home_moneyline)
                        st.metric("Market Win", format_probability_display(home_market_prob))
                        st.metric("Fair ML", home_fair_moneyline)
                        st.markdown(format_edge_badge(f"{row['Home']} Edge", home_edge_value), unsafe_allow_html=True)

                    detail_col_1, detail_col_2, detail_col_3 = st.columns(3)
                    with detail_col_1:
                        st.caption("Consensus Win Probabilities")
                        st.write(consensus_probability_label)
                    with detail_col_2:
                        hold_display = f"{float(row['Hold %']):.1f}%" if pd.notna(row.get("Hold %")) else "N/A"
                        st.caption("Market Hold")
                        st.write(hold_display)
                    with detail_col_3:
                        total_diff_display = f"{float(total_diff_value):+.2f}" if pd.notna(total_diff_value) else "N/A"
                        st.caption("Total Difference")
                        st.write(total_diff_display)

    st.markdown('</div>', unsafe_allow_html=True)


def render_editable_board(display_df):
    with st.expander("Model Controls / Manual Adjustments", expanded=False):
        st.markdown('<div class="section-panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Editable Model Board</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-subtitle">Model outputs stay locked for consistency. Inputs remain editable so you can adjust the board without changing any underlying calculations.</div>',
            unsafe_allow_html=True,
        )

        edited_df = st.data_editor(
            display_df,
            hide_index=True,
            use_container_width=True,
            disabled=[
                "Away",
                "Home",
                "A Hand",
                "H Hand",
                "Away Runs",
                "Home Runs",
                "Away Win",
                "Home Win",
                "Away Implied %",
                "Home Implied %",
                "Away No-Vig %",
                "Home No-Vig %",
                "Hold %",
                "Away Consensus %",
                "Home Consensus %",
                "Consensus Hold Avg",
                "Consensus Books Used",
                "Away Fair ML",
                "Home Fair ML",
                "Away Edge %",
                "Home Edge %",
                "Away EV",
                "Home EV",
                "Projected Total",
                "Total Diff",
                "Over Edge %",
                "Under Edge %",
                "Over EV",
                "Under EV",
                "Best Total Bet",
                "Total Bet Flag",
                "Favorite",
                "Win Edge",
                "Park",
                "Weather",
                "Best Bet",
                "Bet Flag",
            ],
            column_config={
                "Away": st.column_config.TextColumn("Away"),
                "Home": st.column_config.TextColumn("Home"),
                "Away Pitcher": st.column_config.TextColumn("Away Pitcher"),
                "Home Pitcher": st.column_config.TextColumn("Home Pitcher"),
                "A Hand": st.column_config.TextColumn("A Hand"),
                "H Hand": st.column_config.TextColumn("H Hand"),
                "Away SP": st.column_config.NumberColumn("Away SP", format="%.2f"),
                "Home SP": st.column_config.NumberColumn("Home SP", format="%.2f"),
                "Away BP Fatigue": st.column_config.NumberColumn("Away BP", format="%.2f"),
                "Home BP Fatigue": st.column_config.NumberColumn("Home BP", format="%.2f"),
                "Away Lineup": st.column_config.NumberColumn("Away LU", format="%.2f"),
                "Home Lineup": st.column_config.NumberColumn("Home LU", format="%.2f"),
                "Manual Wx": st.column_config.CheckboxColumn("Manual Wx"),
                "Temp": st.column_config.NumberColumn("Temp", format="%d"),
                "Wind": st.column_config.NumberColumn("Wind", format="%.2f"),
                "Away Moneyline": st.column_config.NumberColumn("Away ML", format="%d"),
                "Home Moneyline": st.column_config.NumberColumn("Home ML", format="%d"),
                "Total Line": st.column_config.NumberColumn("Total", format="%.1f"),
                "Over Price": st.column_config.NumberColumn("Over", format="%d"),
                "Under Price": st.column_config.NumberColumn("Under", format="%d"),
                "Sportsbook": st.column_config.TextColumn("Sportsbook"),
                "Away Runs": st.column_config.NumberColumn("Away Runs", format="%.2f"),
                "Home Runs": st.column_config.NumberColumn("Home Runs", format="%.2f"),
                "Away Win": st.column_config.ProgressColumn("Away Win", min_value=0.0, max_value=100.0, format="%.1f%%"),
                "Home Win": st.column_config.ProgressColumn("Home Win", min_value=0.0, max_value=100.0, format="%.1f%%"),
                "Away Implied %": st.column_config.NumberColumn("Away Impl", format="%.1f%%"),
                "Home Implied %": st.column_config.NumberColumn("Home Impl", format="%.1f%%"),
                "Away No-Vig %": st.column_config.NumberColumn("Away NV", format="%.1f%%"),
                "Home No-Vig %": st.column_config.NumberColumn("Home NV", format="%.1f%%"),
                "Hold %": st.column_config.NumberColumn("Hold", format="%.1f%%"),
                "Away Consensus %": st.column_config.NumberColumn("Away Cons", format="%.1f%%"),
                "Home Consensus %": st.column_config.NumberColumn("Home Cons", format="%.1f%%"),
                "Consensus Hold Avg": st.column_config.NumberColumn("Avg Hold", format="%.1f%%"),
                "Consensus Books Used": st.column_config.NumberColumn("Books", format="%d"),
                "Away Fair ML": st.column_config.NumberColumn("Away Fair", format="%d"),
                "Home Fair ML": st.column_config.NumberColumn("Home Fair", format="%d"),
                "Away Edge %": st.column_config.NumberColumn("Away Edge", format="%.1f%%"),
                "Home Edge %": st.column_config.NumberColumn("Home Edge", format="%.1f%%"),
                "Away EV": st.column_config.NumberColumn("Away EV", format="%.1f%%"),
                "Home EV": st.column_config.NumberColumn("Home EV", format="%.1f%%"),
                "Projected Total": st.column_config.NumberColumn("Proj Total", format="%.2f"),
                "Total Diff": st.column_config.NumberColumn("Total Diff", format="%.2f"),
                "Over Edge %": st.column_config.NumberColumn("Over Edge", format="%.1f%%"),
                "Under Edge %": st.column_config.NumberColumn("Under Edge", format="%.1f%%"),
                "Over EV": st.column_config.NumberColumn("Over EV", format="%.1f%%"),
                "Under EV": st.column_config.NumberColumn("Under EV", format="%.1f%%"),
                "Best Total Bet": st.column_config.TextColumn("Best Total"),
                "Total Bet Flag": st.column_config.TextColumn("Total Flag"),
                "Favorite": st.column_config.TextColumn("Favorite"),
                "Win Edge": st.column_config.NumberColumn("Win Edge", format="%.1f%%"),
                "Park": st.column_config.NumberColumn("Park", format="%.2f"),
                "Weather": st.column_config.NumberColumn("Weather", format="%.2f"),
                "Best Bet": st.column_config.TextColumn("Best Bet"),
                "Bet Flag": st.column_config.TextColumn("Bet Flag"),
            },
        )
        st.markdown('</div>', unsafe_allow_html=True)
    return edited_df


inject_app_styles()
initialize_database()
render_header()

tabs = st.tabs([
    "Daily Board",
    "Drivers",
    "Standings",
    "Performance",
])

if "run_dispersion" not in st.session_state:
    st.session_state["run_dispersion"] = float(DEFAULT_RUN_DISPERSION)

if "daily_board_inputs" not in st.session_state:
    reload_automated_inputs()

pitcher_ratings = st.session_state["pitcher_ratings"]
stadium_locations = st.session_state["stadium_locations"]
hitter_ratings = st.session_state["hitter_ratings"]
projected_lineups = st.session_state["projected_lineups"]
live_odds_market_data = st.session_state.get("live_odds_market_data", {})
run_dispersion = float(st.session_state.get("run_dispersion", DEFAULT_RUN_DISPERSION))
daily_board_inputs = st.session_state["daily_board_inputs"].copy()

display_df = build_display_dataframe(
    daily_board_inputs=daily_board_inputs,
    pitcher_ratings=pitcher_ratings,
    team_ratings=team_ratings,
    live_odds_market_data=live_odds_market_data,
    run_dispersion=run_dispersion,
    sims=DEFAULT_SIMS,
)
download_csv = display_df.to_csv(index=False)

if "simulation_last_updated" not in st.session_state:
    set_board_timestamp("simulation_last_updated")
if "odds_last_updated" not in st.session_state and st.session_state.get("live_odds_market_data"):
    set_board_timestamp("odds_last_updated")
if "model_data_last_updated" not in st.session_state:
    set_board_timestamp("model_data_last_updated")

render_global_status_strip()

with tabs[0]:
    render_tab_intro(
        "Daily board",
        "Today’s betting board",
        "Scan the active slate, sort by edge or EV, and compare the model to the market without leaving the daily workflow.",
    )
    render_controls_panel()
    top_plays_df, filtered_display_df, board_view_mode = render_daily_board_drawer(
        display_df,
        download_csv,
        run_dispersion,
    )
    if filtered_display_df.empty:
        render_board_empty_state(display_df, filtered_display_df)
    elif board_view_mode == "Table":
        render_matchup_table(filtered_display_df)
    else:
        render_matchup_cards(filtered_display_df)
    edited_display_df = render_editable_board(display_df)

with tabs[1]:
    render_season_monitor(
        team_ratings,
        pitcher_ratings_df=pitcher_ratings,
        hitter_ratings_df=hitter_ratings,
        projected_lineups_df=projected_lineups,
        daily_board_inputs=daily_board_inputs,
    )

with tabs[2]:
    render_current_standings(team_ratings)

with tabs[3]:
    render_tab_intro(
        "Performance",
        "Tracking and review",
        "Monitor grading, CLV, tracked-bet lifecycle coverage, and archived board snapshots from one performance workspace.",
    )
    render_performance_summary(GRADED_RESULTS_PATH)
    render_clv_summary()
    render_tracked_bet_lifecycle_summary()
    with st.expander("Workflow Tools", expanded=False):
        render_results_grading(GRADED_RESULTS_PATH, HISTORY_DIR)
        render_history_viewer(HISTORY_DIR)

edited_inputs = edited_display_df[INPUT_COLUMNS].copy()

for idx, edited_row in edited_inputs.iterrows():
    away_team_name = edited_row["Away"]
    home_team_name = edited_row["Home"]
    away_pitcher_name = edited_row["Away Pitcher"]
    home_pitcher_name = edited_row["Home Pitcher"]

    edited_inputs.at[idx, "A Hand"] = get_pitcher_throws(
        away_pitcher_name,
        pitcher_ratings,
    )
    edited_inputs.at[idx, "H Hand"] = get_pitcher_throws(
        home_pitcher_name,
        pitcher_ratings,
    )

    if not bool(edited_row["Manual Wx"]):
        default_weather = get_default_weather(home_team_name, stadium_locations)
        edited_inputs.at[idx, "Temp"] = default_weather["Temp"]
        edited_inputs.at[idx, "Wind"] = default_weather["Wind"]

    if pd.isna(edited_inputs.at[idx, "Away Lineup"]):
        edited_inputs.at[idx, "Away Lineup"] = get_default_lineup_adjustment(
            away_team_name,
            hitter_ratings,
            projected_lineups,
        )

    if pd.isna(edited_inputs.at[idx, "Home Lineup"]):
        edited_inputs.at[idx, "Home Lineup"] = get_default_lineup_adjustment(
            home_team_name,
            hitter_ratings,
            projected_lineups,
        )

if not edited_inputs.equals(st.session_state["daily_board_inputs"]):
    st.session_state["daily_board_inputs"] = edited_inputs
    st.rerun()
