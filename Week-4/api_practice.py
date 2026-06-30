"""
Week 4 Practice: Call a Public API

This is a small, standalone exercise focused on ONE thing:
making a basic GET request and reading the JSON response.
(Separate from the weather_cli.py deliverable.)

API used: GitHub's public API (https://api.github.com)
No API key required for basic read-only requests.
"""

import sys
import requests

API_URL = "https://api.github.com/users/{username}"

# GitHub asks anonymous API clients to set a User-Agent header.
# It doesn't raise the rate limit, but it's good practice.
HEADERS = {"User-Agent": "week4-api-practice-script"}


def get_github_profile(username):
    """Fetch basic public profile info for a GitHub username."""
    url = API_URL.format(username=username)

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 403 and "rate limit" in response.text.lower():
            print(
                "GitHub's anonymous rate limit (60 requests/hour per IP) "
                "has been hit. Wait a bit and try again, or see the "
                "'rate limit' note in the README."
            )
            return None

        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        print(f"Request failed: {error}")
        return None

    return response.json()


def print_profile(data):
    """Print a few key fields from the API response."""
    if data is None:
        print("No data to display.")
        return

    print("-" * 30)
    print(f"Username:    {data.get('login')}")
    print(f"Name:        {data.get('name')}")
    print(f"Bio:         {data.get('bio')}")
    print(f"Public repos:{data.get('public_repos')}")
    print(f"Followers:   {data.get('followers')}")
    print("-" * 30)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Allow usage like: python api_practice.py torvalds
        username = sys.argv[1]
    else:
        username = input("Enter a GitHub username: ").strip()

    profile_data = get_github_profile(username)
    print_profile(profile_data)