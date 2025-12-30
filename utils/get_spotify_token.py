import base64
import logging
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")


async def get_spotify_token():
    logging.info("Fetching Spotify token...")
    logging.info("SPOTIFY_CLIENT_ID:", SPOTIFY_CLIENT_ID[:5] + "..." if SPOTIFY_CLIENT_ID else None)
    logging.info("SPOTIFY_CLIENT_SECRET:", SPOTIFY_CLIENT_SECRET[:5] + "..." if SPOTIFY_CLIENT_SECRET else None)

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("❌ SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET is missing. Check your .env and load_dotenv()")

    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "client_credentials"}

    async with httpx.AsyncClient() as client:
        response = await client.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
        print("[Spotify] Status:", response.status_code)
        print("[Spotify] Body:", response.text)

        if response.status_code != 200:
            raise RuntimeError("❌ Failed to get token from Spotify")

        token = response.json().get("access_token")
        print("[Spotify] Access token:", token[:10] + "...")

        return token
