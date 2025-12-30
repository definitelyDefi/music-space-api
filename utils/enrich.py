import os
from dotenv import load_dotenv
import httpx
import asyncio
import json
load_dotenv()  # must be called first

DISCOGS_KEY = os.getenv("DISCOGS_CONSUMER_KEY")
DISCOGS_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET")
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")


async def enrich_track(track: dict, SPOTIFY_TOKEN=None, debug=False) -> dict:
    """
    Enrich a single track with Discogs metadata and missing streaming links (Spotify, Deezer, SoundCloud).
    """
   
    query = f"{track.get('artist')} {track.get('title')}"
    
    async with httpx.AsyncClient(timeout=10) as client:
        # --- 1. Discogs enrichment ---
        try:
            r = await client.get(
                "https://api.discogs.com/database/search",
                params={
                    "q": query,
                    "type": "release",
                    "per_page": 1,
                    "key": DISCOGS_KEY,
                    "secret": DISCOGS_SECRET
                }
            )
            
            data = r.json()
            with open("discogs_response.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if r.status_code == 200 and data.get("results"):
                result = data["results"][0]
                if debug:
                    print(f"[Discogs Result] {track.get('title')} -> {result}")

                def merge_list(field, new_values):
                    if new_values:
                        track[field] = list(set(track.get(field, [])).union(new_values))

                merge_list("genre", result.get("genre"))
                merge_list("style", result.get("style"))
                merge_list("label", result.get("label"))
                merge_list("format", result.get("format"))

                if not track.get("year"):
                    track["year"] = result.get("year") or (result.get("released") or "").split("-")[0]

                # Cover image
                if not track.get("cover_url") or "2a96cbd8b46e442fc41c2b86b821562f" in track.get("cover_url", ""):
                    if result.get("cover_image"):
                        track["cover_url"] = result["cover_image"]

                if debug:
                    print(f"[Discogs Enriched] {track.get('title')} -> cover: {track.get('cover_url')}")

            else:
                if debug:
                    print(f"[Discogs Empty] {track.get('title')} -> {data}")

        except Exception as e:
            print(f"[Discogs Error] {track.get('title')}: {e}")

        # --- 2. Spotify URL ---
        if not track.get("spotify_url") and SPOTIFY_TOKEN:
            try:
                headers = {"Authorization": f"Bearer {SPOTIFY_TOKEN}"}
                r = await client.get(
                    "https://api.spotify.com/v1/search",
                    headers=headers,
                    params={"q": query, "type": "track", "limit": 1}
                )
                items = r.json().get("tracks", {}).get("items", [])
                if items:
                    track["spotify_url"] = items[0]["external_urls"]["spotify"]
                    if debug:
                        print(f"[Spotify URL] {track['title']} -> {track['spotify_url']}")
            except Exception as e:
                if debug:
                    print(f"[Spotify Error] {track.get('title')}: {e}")

        # --- 3. Deezer URL ---
        if not track.get("deezer_url"):
            try:
                r = await client.get(f"https://api.deezer.com/search/track?q={query}")
                data = r.json()
                if data.get("data"):
                    track["deezer_url"] = data["data"][0].get("link")
                    if debug:
                        print(f"[Deezer URL] {track['title']} -> {track['deezer_url']}")
            except Exception as e:
                if debug:
                    print(f"[Deezer Error] {track.get('title')}: {e}")

        # --- 4. SoundCloud URL ---
        if not track.get("soundcloud_url") and SOUNDCLOUD_CLIENT_ID:
            try:
                r = await client.get(
                    "https://api-v2.soundcloud.com/search/tracks",
                    params={"q": query, "client_id": SOUNDCLOUD_CLIENT_ID, "limit": 1}
                )
                collection = r.json().get("collection", [])
                if collection:
                    track["soundcloud_url"] = collection[0].get("permalink_url")
                    if debug:
                        print(f"[SoundCloud URL] {track['title']} -> {track['soundcloud_url']}")
            except Exception as e:
                if debug:
                    print(f"[SoundCloud Error] {track.get('title')}: {e}")

        # --- 5. Last.fm fallback link if missing ---
        if not track.get("lastfm_url"):
            track["lastfm_url"] = f"https://www.last.fm/music/{track.get('artist', '').replace(' ', '+')}/_/{track.get('title', '').replace(' ', '+')}"
            if debug:
                print(f"[Last.fm URL] {track['title']} -> {track['lastfm_url']}")

    return track
async def enrich_artist_metadata(artist_name: str, lastfm_key: str, soundcloud_client_id: str, spotify_token: str, deezer_client=None) -> dict:
    """Enrich a single artist with Last.fm, Spotify, Deezer, SoundCloud URLs and image if available."""
    enriched = {"name": artist_name}

    # --- Last.fm enrichment ---
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "http://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.getinfo",
                    "artist": artist_name,
                    "api_key": lastfm_key,
                    "format": "json"
                }
            )
            if res.status_code == 200:
                info = res.json().get("artist", {})
                enriched["lastfm_url"] = info.get("url")
                enriched["genres"] = [t["name"] for t in info.get("tags", {}).get("tag", [])[:3]]
    except Exception as e:
        print(f"[Last.fm Error] {artist_name}: {e}")
        

    # --- Deezer enrichment ---
    try:
        async with httpx.AsyncClient() as client:
            search_res = await client.get(f"https://api.deezer.com/search/artist?q={artist_name}")
            if search_res.status_code == 200 and search_res.json().get("data"):
                artist_data = search_res.json()["data"][0]
                enriched["deezer_url"] = artist_data.get("link")
                enriched["image_url"] = artist_data.get("picture_medium")
    except Exception as e:
        print(f"[Deezer Error] {artist_name}: {e}")

    # --- Spotify enrichment ---
    try:
        headers = {"Authorization": f"Bearer {spotify_token}"}
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api.spotify.com/v1/search",
                params={"q": artist_name, "type": "artist", "limit": 1},
                headers=headers
            )
            items = res.json().get("artists", {}).get("items", [])
            if items:
                item = items[0]
                enriched["spotify_url"] = item.get("external_urls", {}).get("spotify")
                if "image_url" not in enriched:
                    enriched["image_url"] = item.get("images", [{}])[0].get("url")
    except Exception as e:
        print(f"[Spotify Error] {artist_name}: {e}")
        

    # --- SoundCloud enrichment ---
    # --- SoundCloud enrichment ---
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api-v2.soundcloud.com/search/users",
                params={"q": artist_name, "client_id": soundcloud_client_id, "limit": 1},
                timeout=10
            )
            if res.status_code == 200:
                try:
                    data = res.json()
                    collection = data.get("collection", [])
                    if collection:
                        sc_artist = collection[0]
                        enriched["soundcloud_url"] = f"https://soundcloud.com/{sc_artist.get('permalink')}"
                        if "image_url" not in enriched:
                            enriched["image_url"] = sc_artist.get("avatar_url")
                except Exception:
                    print(f"[SoundCloud Error] Failed to parse JSON for artist: {artist_name}")
    except Exception:
        print(f"[SoundCloud Error] Request failed for artist: {artist_name}")

    return enriched