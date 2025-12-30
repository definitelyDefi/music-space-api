from utils.deezer import fetch_deezer_recommended_artists
from utils.lastfm import fetch_lastfm_recommended_artists
from utils.soundcloud import fetch_soundcloud_recommended_artists
from utils.spotify import fetch_spotify_recommended_artists
import httpx
from typing import Optional

def normalize(t):
    return (t["title"].lower().strip(), t["artist"].lower().strip())

async def get_fallback_image(artist_name: str, client: httpx.AsyncClient) -> Optional[str]:
    try:
        wiki_resp = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{artist_name.replace(' ', '_')}"
        )
        if wiki_resp.status_code == 200:
            wiki_data = wiki_resp.json()
            image_url = wiki_data.get("thumbnail", {}).get("source")
            if image_url:
                return image_url
    except Exception:
        pass
    return None

def normalize_artist_entry(artist, seen_names):
    name = artist["name"].strip().lower()
    if name in seen_names:
        return None
    seen_names.add(name)

    return {
        "name": artist["name"],
        "image_url": artist.get("image_url"),
        "genres": artist.get("genres", []),
        "links": {
            "spotify": artist.get("spotify_url"),
            "deezer": artist.get("deezer_url"),
            "soundcloud": artist.get("soundcloud_url"),
            "lastfm": artist.get("lastfm_url"),
        },
        "source": artist.get("source", [])
    }
    
async def get_all_recommended_artists(artist_name, artist_id, client, headers, lastfm_key, soundcloud_id):
    spotify = await fetch_spotify_recommended_artists(client, headers, artist_id)
    deezer = await fetch_deezer_recommended_artists(client, artist_name)
    lastfm = await fetch_lastfm_recommended_artists(client, artist_name, lastfm_key)
    soundcloud = await fetch_soundcloud_recommended_artists(client, artist_name, soundcloud_id)

    combined = spotify + deezer + lastfm + soundcloud
    seen = set()
    normalized = []

    for artist in combined:
        entry = normalize_artist_entry(artist, seen)
        if entry:
            normalized.append(entry)

    return normalized