import logging
from typing import Optional
from fastapi import FastAPI, Query
from dotenv import load_dotenv
import os
import httpx
import base64
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()
# Load environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or "*" to allow all during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
        
@app.get("/recommendations/by-track")
async def recommendations_by_track(track: str = Query(..., description="Track name")):
    # Split into title + artist if formatted like "Title - Artist"
    if " - " in track:
        track_title, track_artist = map(str.strip, track.split(" - ", 1))
        track_title = track_title.lower()
        track_artist = track_artist.lower()
    else:
        track_title = track
        track_artist = None
    print(f"Track Title: {track_title}, Track Artist: {track_artist}")
    try:
        print("[DEBUG] About to fetch Spotify token")
        token = await get_spotify_token()
        print("[DEBUG] Spotify token fetched")
        print("[DEBUG] Spotify token starts with:", token[:20])
        if not token:
            raise ValueError("Spotify token is missing")
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print("[Token Error]", e)
        return {"error": "Failed to get Spotify token"}

    def normalize(t):
        return (t["title"].lower().strip(), t["artist"].lower().strip())

    def make_track(t):
        return {
            "title": t["title"],
            "artist": t["artist"],
            "duration_ms": t.get("duration_ms") or t.get("duration_sec", 0) * 1000,
            "cover_url": t.get("cover"),
            "preview_url": t.get("preview_url"),
            "spotify_url": t.get("spotify_url"),
            "deezer_url": t.get("deezer_url"),
            "source": t["source"]
        }

    spotify_tracks = []
    deezer_tracks = []
    lastfm_tracks = []
    artist_metadata = {}

    async with httpx.AsyncClient() as client:
       # ---------------- Spotify Search to Determine Artist ----------------
        try:
            # Step 1: build free-text query
            query_text = f"{track_title} {track_artist}" if track_artist else track_title

            print(f"[Spotify Search] Trying free-text query: '{query_text}'")

            search_resp = await client.get(
                "https://api.spotify.com/v1/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                params={"q": query_text, "type": "track", "limit": 1}
            )

            if search_resp.status_code != 200:
                print(f"[Spotify ERROR {search_resp.status_code}] {search_resp.text}")
                raise ValueError("Spotify search failed.")

            items = search_resp.json().get("tracks", {}).get("items", [])

            # Step 2: fallback to strict search
            if not items and track_artist:
                strict_q = f'track:"{track_title}" artist:"{track_artist}"'
                print(f"[Spotify Fallback] Trying strict query: '{strict_q}'")

                fallback_resp = await client.get(
                    "https://api.spotify.com/v1/search",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    params={"q": strict_q, "type": "track", "limit": 1}
                )

                if fallback_resp.status_code != 200:
                    print(f"[Spotify Fallback ERROR {fallback_resp.status_code}] {fallback_resp.text}")
                    raise ValueError("Spotify fallback search failed.")

                items = fallback_resp.json().get("tracks", {}).get("items", [])

            if not items:
                raise ValueError(f"Track '{track}' not found on Spotify.")

            artist_id = items[0]["artists"][0]["id"]
            artist_name = items[0]["artists"][0]["name"]
            print(f"[Spotify] Found artist: {artist_name} ({artist_id})")

        except Exception as e:
            print("[Spotify Track Search Error]:", e)
            return {"error": "Could not determine artist from track."}

        # ---------------- Spotify: Artist Metadata + Tracks ----------------
        try:
            artist_info_resp = await client.get(f"https://api.spotify.com/v1/artists/{artist_id}", headers=headers)
            genres = artist_info_resp.json().get("genres", [])
            artist_image = artist_info_resp.json().get("images", [{}])[0].get("url")
            artist_metadata = {
                "name": artist_name,
                "image_url": artist_image,
                "genres": genres
            }

            top_resp = await client.get(
                f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
                headers=headers,
                params={"market": "US"}
            )
            for t in top_resp.json().get("tracks", [])[:5]:
                spotify_tracks.append({
                    "title": t["name"],
                    "artist": t["artists"][0]["name"],
                    "duration_ms": t["duration_ms"],
                    "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                    "preview_url": t.get("preview_url"),
                    "spotify_url": t["external_urls"]["spotify"],
                    "deezer_url": None,
                    "source": ["Spotify"]
                })

            rel_resp = await client.get(
                f"https://api.spotify.com/v1/artists/{artist_id}/related-artists",
                headers=headers
            )
            related = rel_resp.json().get("artists", [])[:10]
            for rel in related:
                rel_top = await client.get(
                    f"https://api.spotify.com/v1/artists/{rel['id']}/top-tracks",
                    headers=headers,
                    params={"market": "US"}
                )
                for t in rel_top.json().get("tracks", [])[:2]:
                    spotify_tracks.append({
                        "title": t["name"],
                        "artist": t["artists"][0]["name"],
                        "duration_ms": t["duration_ms"],
                        "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                        "preview_url": t.get("preview_url"),
                        "spotify_url": t["external_urls"]["spotify"],
                        "deezer_url": None,
                        "source": ["Spotify"]
                    })
        except Exception as e:
            print("[Spotify Artist Error]:", e)

        # ---------------- Deezer: Top Tracks by Artist ----------------
        try:
            d_search = await client.get(f"https://api.deezer.com/search/artist?q={artist_name}")
            d_data = d_search.json().get("data", [])
            if d_data:
                d_id = d_data[0]["id"]
                d_top = await client.get(f"https://api.deezer.com/artist/{d_id}/top?limit=5")
                for t in d_top.json()["data"]:
                    deezer_tracks.append({
                        "title": t["title"],
                        "artist": t["artist"]["name"],
                        "duration_sec": t["duration"],
                        "cover": t["album"]["cover_big"],
                        "preview_url": t["preview"],
                        "spotify_url": None,
                        "deezer_url": t["link"],
                        "source": ["Deezer"]
                    })
        except Exception as e:
            print("[Deezer Error]:", e)

        # ---------------- Last.fm: Top Track of Similar Artists ----------------
        try:
            lastfm_similar = await client.get("http://ws.audioscrobbler.com/2.0/", params={
                "method": "artist.getsimilar",
                "artist": artist_name,
                "api_key": LASTFM_API_KEY,
                "format": "json",
                "limit": 10
            })
            similar = lastfm_similar.json().get("similarartists", {}).get("artist", [])
            for a in similar:
                top_resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
                    "method": "artist.gettoptracks",
                    "artist": a["name"],
                    "api_key": LASTFM_API_KEY,
                    "format": "json",
                    "limit": 1
                })
                top_tracks = top_resp.json().get("toptracks", {}).get("track", [])
                if top_tracks:
                    t = top_tracks[0]
                    lastfm_tracks.append({
                        "title": t["name"],
                        "artist": a["name"],
                        "duration_sec": int(t.get("duration", 0)),
                        "cover": t["image"][-1]["#text"] if t.get("image") else None,
                        "preview_url": None,
                        "spotify_url": None,
                        "deezer_url": t.get("url"),
                        "source": ["Last.fm"]
                    })
        except Exception as e:
            print("[Last.fm Error]:", e)

    # ---------------- Merge & Deduplicate ----------------
    combined = {}
    for t in spotify_tracks + deezer_tracks + lastfm_tracks:
        key = normalize(t)
        if key in combined:
            combined[key]["source"] = list(set(combined[key]["source"] + t["source"]))
            if t.get("spotify_url"):
                combined[key]["spotify_url"] = t["spotify_url"]
            if t.get("deezer_url"):
                combined[key]["deezer_url"] = t["deezer_url"]
        else:
            combined[key] = t

    return {
        "artist": artist_metadata,
        "recommended_tracks": [make_track(t) for t in combined.values()]
    }
    import base64


@app.get("/token")
async def get_spotify_tokenn():
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {auth_header}"},
            data={"grant_type": "client_credentials"},
        )
        res.raise_for_status()
        token_data = res.json()
        return {"access_token": token_data["access_token"]}






@app.get("/recommendations/by-artist")
async def recommendations_by_artist(artist: str = Query(...)):
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    def normalize(track):
        return (track["title"].lower().strip(), track["artist"].lower().strip())

    def make_track(track):
        return {
            "title": track["title"],
            "artist": track["artist"],
            "duration_ms": track.get("duration_ms") or track.get("duration_sec", 0) * 1000,
            "cover_url": track.get("cover"),
            "preview_url": track.get("preview_url"),
            "spotify_url": track.get("spotify_url"),
            "deezer_url": track.get("deezer_url"),
            "source": track["source"]
        }

    async with httpx.AsyncClient() as client:
        # --- Search Artist on Spotify ---
        search_resp = await client.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": f'artist:"{artist}"', "type": "artist", "limit": 1}
        )
        items = search_resp.json().get("artists", {}).get("items", [])
        if not items:
            return {"error": f"Artist '{artist}' not found on Spotify."}

        artist_id = items[0]["id"]
        artist_name = items[0]["name"]
        artist_image = items[0]["images"][0]["url"] if items[0]["images"] else None

        artist_info_resp = await client.get(f"https://api.spotify.com/v1/artists/{artist_id}", headers=headers)
        genres = artist_info_resp.json().get("genres", [])

        artist_metadata = {
            "name": artist_name,
            "image_url": artist_image,
            "genres": genres
        }

        # --- Spotify Top Tracks ---
        spotify_top = []
        top_resp = await client.get(
            f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
            headers=headers, params={"market": "US"}
        )
        for t in top_resp.json().get("tracks", [])[:10]:
            spotify_top.append({
                "title": t["name"],
                "artist": t["artists"][0]["name"],
                "duration_ms": t["duration_ms"],
                "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                "preview_url": t.get("preview_url"),
                "spotify_url": t["external_urls"]["spotify"],
                "deezer_url": None,
                "source": ["Spotify"]
            })

        # --- Deezer Top Tracks ---
        deezer_top = []
        try:
            d_search = await client.get(f"https://api.deezer.com/search/artist?q={artist}")
            d_data = d_search.json().get("data", [])
            if d_data:
                d_id = d_data[0]["id"]
                d_top = await client.get(f"https://api.deezer.com/artist/{d_id}/top?limit=10")
                for t in d_top.json()["data"]:
                    deezer_top.append({
                        "title": t["title"],
                        "artist": t["artist"]["name"],
                        "duration_sec": t["duration"],
                        "cover": t["album"]["cover_big"],
                        "preview_url": t["preview"],
                        "spotify_url": None,
                        "deezer_url": t["link"],
                        "source": ["Deezer"]
                    })
        except Exception:
            pass

        # --- Combine & Deduplicate Top Tracks ---
        combined = {}
        for t in spotify_top + deezer_top:
            key = normalize(t)
            if key in combined:
                combined[key]["source"] = list(set(combined[key]["source"] + t["source"]))
                if t.get("spotify_url"):
                    combined[key]["spotify_url"] = t["spotify_url"]
                if t.get("deezer_url"):
                    combined[key]["deezer_url"] = t["deezer_url"]
            else:
                combined[key] = t

        top_tracks = [make_track(t) for t in combined.values()]

        # --- Related Artists ---
        related = []
        related_artists_data = []
        rel_resp = await client.get(f"https://api.spotify.com/v1/artists/{artist_id}/related-artists", headers=headers)
    
        # Spotify related artists
        if rel_resp.status_code == 200:
            related = rel_resp.json().get("artists", [])[:8]
            for r in related:
                related_artists_data.append({
                    "name": r["name"],
                    "image_url": r["images"][0]["url"] if r.get("images") else None,
                    "genres": r.get("genres", []),
                    "spotify_url": r["external_urls"]["spotify"],
                    "deezer_url": None  # Will try to fetch below
                })
                # Try to enrich with Deezer link
                try:
                    d_artist = await client.get(f"https://api.deezer.com/search/artist?q={r['name']}")
                    d_data = d_artist.json().get("data", [])
                    if d_data:
                        related_artists_data[-1]["deezer_url"] = d_data[0]["link"]
                except Exception:
                    pass
       # Last.fm fallback if related artists not found
        if not related:
            print("[Fallback] No related artists from Spotify. Using Last.fm.")
            lastfm_resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
                "method": "artist.getsimilar",
                "artist": artist_name,
                "api_key": LASTFM_API_KEY,
                "format": "json",
                "limit": 10
            })
            similar = lastfm_resp.json().get("similarartists", {}).get("artist", [])
            for a in similar:
                entry = {
                    "name": a["name"],
                    "image_url": a.get("image", [{}])[-1].get("#text") or None,
                    "genres": [],
                    "spotify_url": None,
                    "deezer_url": None
                }
                # Replace if image is a known placeholder
                if not entry["image_url"] or "2a96cbd8b46e442fc41c2b86b821562f.png" in entry["image_url"]:
                    fallback = await get_fallback_image(entry["name"], client)
                    if fallback:
                        entry["image_url"] = fallback

                # Optional: try to find Spotify URL
                try:
                    s_artist = await client.get("https://api.spotify.com/v1/search", headers=headers, params={
                        "q": f'artist:"{a["name"]}"', "type": "artist", "limit": 1
                    })
                    s_data = s_artist.json().get("artists", {}).get("items", [])
                    if s_data:
                        entry["spotify_url"] = s_data[0]["external_urls"]["spotify"]
                        entry["genres"] = s_data[0].get("genres", [])
                except Exception:
                    pass

                # Optional: try to find Deezer URL
                try:
                    d_artist = await client.get(f"https://api.deezer.com/search/artist?q={a['name']}")
                    d_data = d_artist.json().get("data", [])
                    if d_data:
                        entry["deezer_url"] = d_data[0]["link"]
                except Exception:
                    pass

                related_artists_data.append(entry)

        # --- Fetch Recommended Tracks from Related Artists ---
        recommended = {}
        for rel_artist in related_artists_data:
            rel_name = rel_artist["name"]
            rel_url = rel_artist.get("spotify_url", "")
            rel_id = rel_url.split("/")[-1] if "open.spotify.com/artist/" in rel_url else None

            # Spotify top 1 track
            if rel_id:
                try:
                    s_resp = await client.get(
                        f"https://api.spotify.com/v1/artists/{rel_id}/top-tracks",
                        headers=headers, params={"market": "US"}
                    )
                    for t in s_resp.json().get("tracks", [])[:1]:
                        track_data = {
                            "title": t["name"],
                            "artist": t["artists"][0]["name"],
                            "duration_ms": t["duration_ms"],
                            "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                            "preview_url": t.get("preview_url"),
                            "spotify_url": t["external_urls"]["spotify"],
                            "deezer_url": None,
                            "source": ["Spotify"]
                        }
                        key = normalize(track_data)
                        if key not in recommended:
                            recommended[key] = track_data
                except Exception:
                    continue

            # Deezer fallback
            try:
                d_search = await client.get(f"https://api.deezer.com/search/artist?q={rel_name}")
                d_data = d_search.json().get("data", [])
                if d_data:
                    d_id = d_data[0]["id"]
                    d_top = await client.get(f"https://api.deezer.com/artist/{d_id}/top?limit=1")
                    for t in d_top.json().get("data", []):
                        track_data = {
                            "title": t["title"],
                            "artist": t["artist"]["name"],
                            "duration_sec": t["duration"],
                            "cover": t["album"]["cover_big"],
                            "preview_url": t["preview"],
                            "spotify_url": None,
                            "deezer_url": t["link"],
                            "source": ["Deezer"]
                        }
                        key = normalize(track_data)
                        if key in recommended:
                            recommended[key]["source"] = list(set(recommended[key]["source"] + ["Deezer"]))
                            recommended[key]["deezer_url"] = track_data["deezer_url"]
                        else:
                            recommended[key] = track_data
            except Exception:
                continue

        recommended_tracks = [make_track(t) for t in recommended.values()]

        return {
            "artist": artist_metadata,
            "top_tracks": top_tracks,
            "recommended_tracks": recommended_tracks,
            "related_artists": related_artists_data
        }