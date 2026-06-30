"""
Week 4 Deliverable: Simple API-based Python Project

A command-line weather lookup tool.

this script demonstrates (Week 4 topics):
- Calling a public API with Python (requests)
- Working with JSON responses
- Basic error handling for network/API calls
- Simple, readable function structure

API used: Open-Meteo (https://open-meteo.com/)
No API key required.
"""

import requests
import sys

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo uses numeric weather codes. This maps the common ones
# to plain English so the output is readable.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}


def get_coordinates(city_name):
    """
    Look up latitude/longitude for a city name using Open-Meteo's
    free geocoding API. Returns a dict with lat, lon, and display name,
    or None if the city couldn't be found.
    """
    params = {"name": city_name, "count": 1}

    try:
        response = requests.get(GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        print(f"Error contacting geocoding service: {error}")
        return None

    data = response.json()
    results = data.get("results")

    if not results:
        return None

    place = results[0]
    return {
        "lat": place["latitude"],
        "lon": place["longitude"],
        "display_name": f"{place['name']}, {place.get('country', '')}".strip(", "),
    }


def get_weather(lat, lon):
    """
    Fetch current weather for a given latitude/longitude.
    Returns a dict of weather data, or None on failure.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
    }

    try:
        response = requests.get(WEATHER_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        print(f"Error contacting weather service: {error}")
        return None

    data = response.json()
    return data.get("current_weather")


def describe_weather_code(code):
    """Convert a numeric weather code into a readable description."""
    return WEATHER_CODES.get(code, f"Unknown conditions (code {code})")


def print_weather_report(city_name):
    """Look up a city, fetch its weather, and print a formatted report."""
    location = get_coordinates(city_name)

    if location is None:
        print(f"Could not find a location matching '{city_name}'.")
        return

    weather = get_weather(location["lat"], location["lon"])

    if weather is None:
        print("Could not retrieve weather data right now.")
        return

    print("-" * 40)
    print(f"Weather report for {location['display_name']}")
    print("-" * 40)
    print(f"Temperature:  {weather['temperature']}°C")
    print(f"Wind speed:   {weather['windspeed']} km/h")
    print(f"Conditions:   {describe_weather_code(weather['weathercode'])}")
    print(f"Observed at:  {weather['time']}")
    print("-" * 40)


def main():
    if len(sys.argv) > 1:
        # Allow usage like: python weather_cli.py Kathmandu
        city = " ".join(sys.argv[1:])
    else:
        city = input("Enter a city name: ").strip()

    if not city:
        print("No city name entered. Exiting.")
        return

    print_weather_report(city)


if __name__ == "__main__":
    main()
