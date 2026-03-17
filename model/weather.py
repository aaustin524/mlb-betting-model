def get_weather_adjustment(temperature_f, wind_factor):
    multiplier = 1.00

    if temperature_f < 60:
        multiplier *= 0.97
    elif temperature_f > 85:
        multiplier *= 1.03

    multiplier *= wind_factor

    return multiplier
