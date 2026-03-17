import pandas as pd
import requests


def _get_local_weather_defaults():
    return {
        "temperature_f": 72,
        "wind_factor": 1.00,
        "weather_source": "local_default",
    }


def _get_live_weather_from_nws(lat, lon):
    """
    Placeholder for National Weather Service integration using api.weather.gov.

    If the request fails or the response is missing expected data, fall back
    to local default weather values.
    """

    headers = {"User-Agent": "mlb-betting-model/1.0"}

    try:
        points_response = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=headers,
            timeout=10,
        )
        points_response.raise_for_status()
        points_data = points_response.json()

        forecast_url = points_data["properties"]["forecast"]

        forecast_response = requests.get(
            forecast_url,
            headers=headers,
            timeout=10,
        )
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        first_period = forecast_data["properties"]["periods"][0]

        return {
            "temperature_f": float(first_period.get("temperature", 72)),
            "wind_factor": 1.00,
            "weather_source": "nws_api",
        }
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return _get_local_weather_defaults()


def load_stadium_locations(file_path="data/stadium_locations.csv", data_mode="local"):
    try:
        if data_mode == "live":
            raise NotImplementedError("Live stadium loading is not implemented yet.")

        return pd.read_csv(file_path)
    except Exception:
        return pd.read_csv(file_path)


def get_weather_for_team(home_team, stadium_df, data_mode="local"):
    """
    Return default weather values for a home team based on stadium location.

    This is set up so live weather can be added later without changing the
    app code that asks for team-based weather defaults.
    """

    stadium_row = stadium_df.loc[stadium_df["team"] == home_team]

    if stadium_row.empty:
        return _get_local_weather_defaults()

    try:
        if data_mode == "live":
            lat = float(stadium_row.iloc[0]["lat"])
            lon = float(stadium_row.iloc[0]["lon"])
            return _get_live_weather_from_nws(lat, lon)

        return _get_local_weather_defaults()
    except Exception:
        return _get_local_weather_defaults()
