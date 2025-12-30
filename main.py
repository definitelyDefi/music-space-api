
import json
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, Query
from dotenv import load_dotenv
import os
import httpx
import base64
from fastapi.middleware.cors import CORSMiddleware
from utils.normalize import get_all_recommended_artists
from utils.deezer import fetch_deezer_related_tracks, fetch_deezer_tracks
from utils.lastfm import fetch_lastfm_similar_tracks, fetch_lastfm_tracks
from utils.make import make_track
from utils.spotify import extract_artist_info_from_spotify, fetch_spotify_tracks_and_metadata
from utils.enrich import enrich_artist_metadata, enrich_track
from utils.soundcloud import get_soundcloud_recommendations
import asyncio
import random
from endpoints.feeling_lucky import router as feeling_lucky_router
from utils.get_spotify_token import get_spotify_token


load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")

app = FastAPI()
app.include_router(feeling_lucky_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or "*" to allow all during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
session_cache = {}

@app.get("/recommendations/by-track")
async def recommendations_by_track_enriched_stream(
    track: str = Query(...),
    limit: int = Query(20),
    offset: int = Query(0),
    shuffle: bool = Query(False),
    include_original: bool = Query(False),
    depth: int = Query(1, ge=1, le=3),
):
    async def event_generator(track_query: str):
        
        print("Request for recommendations by track:", track_query, 
              "limit:", limit, "offset:", offset, "shuffle:", shuffle,
              "include_original:", include_original, "depth:", depth)
        # Split input into title / artist
        if " - " in track_query:
            track_title, track_artist = map(str.strip, track_query.split(" - ", 1))
        else:
            track_title, track_artist = track_query, None

        # --- Auth ---
        try:
            token = await get_spotify_token()
            headers = {"Authorization": f"Bearer {token}"}
        except Exception:
            yield "data: " + json.dumps({"error": "Spotify token error"}) + "\n\n"
            return

        async with httpx.AsyncClient() as client:
            # --- Artist info ---
            try:
                artist_id, artist_name = await extract_artist_info_from_spotify(
                    client, headers, track_title, track_artist
                )
            except Exception:
                yield "data: " + json.dumps({"error": "Could not determine artist"}) + "\n\n"
                return

            # Optionally yield original track
            if include_original and track_artist:
                try:
                    orig_track = {
                        "title": track_title,
                        "artist": track_artist,
                        "source": ["original"]
                    }
                    # Minimal enrichment (just make_track)
                    yield "data: " + json.dumps({"original_track": make_track(orig_track)}) + "\n\n"
                except Exception:
                    pass

            # --- Fetch data from all sources in parallel ---
            tasks = [
                fetch_spotify_tracks_and_metadata(client, headers, artist_id, artist_name, offset=offset, limit=limit),
                fetch_deezer_tracks(client, artist_name, limit=limit, offset=offset),
                fetch_deezer_related_tracks(client, artist_name, limit=limit, offset=offset),
                fetch_lastfm_tracks(client, artist_name, LASTFM_API_KEY, limit=limit, offset=offset),
                fetch_lastfm_similar_tracks(client, artist_name, track_title, LASTFM_API_KEY, limit=limit),
                get_soundcloud_recommendations(track_title, artist_name, client, SOUNDCLOUD_CLIENT_ID, offset=offset, limit=limit),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            spotify_data = results[0] if not isinstance(results[0], Exception) else {"tracks": [], "artist_metadata": None}

            all_tracks_raw = []
            for r in results:
                if isinstance(r, dict) and "tracks" in r:
                    all_tracks_raw += r["tracks"]
                elif isinstance(r, list):
                    all_tracks_raw += r

            # --- Deduplicate ---
            def unique_key(t): return (t["title"].lower(), t["artist"].lower())
            unique = {unique_key(t): t for t in all_tracks_raw}
            all_unique = list(unique.values())

            # --- Debug logging ---
            try:
                with open("debug_tracks.json", "w", encoding="utf-8") as f:
                    import json as _json
                    _json.dump(all_unique, f, ensure_ascii=False, indent=2)
                print(f"[DEBUG] Dumped {len(all_unique)} tracks to debug_tracks.json")
            except Exception as e:
                print("[DEBUG] Failed to write debug_tracks.json:", e)

            # If include_original is False, filter out tracks by the original artist (fuzzy match)
            if not include_original and track_artist:
                ta = track_artist.lower().strip()
                def is_same_artist(candidate: str) -> bool:
                    cand = candidate.lower().strip()
                    return cand == ta or ta in cand or cand in ta
                all_unique = [t for t in all_unique if not is_same_artist(t.get("artist", ""))]

            if shuffle:
                random.shuffle(all_unique)

            # Slice limit
            sliced = all_unique[:limit]

            # --- Stream initial artist metadata ---
            yield "data: " + json.dumps({"artist": spotify_data.get("artist_metadata")}) + "\n\n"

          # --- Enrich and stream tracks one by one ---
            enriched_debug = []
            for t in sliced:
                try:
                    enriched = await enrich_track(t, token)  # <- use the new track-by-track function
                    
                    if enriched.get("image_url") and "2a96cbd8b46e442fc41c2b86b821562f" in enriched["image_url"]:
                        enriched["image_url"] = enriched.get("cover_url")
                    print(f" ENRICHED LASTFM URL: {enriched.get('lastfm_url')}")
                    if not enriched.get("lastfm_url"):
                        enriched["lastfm_url"] = f"https://www.last.fm/music/{enriched['artist'].replace(' ', '+')}/_/{enriched['title'].replace(' ', '+')}"
                        print(f"[Last.fm URL] {enriched['title']} -> {enriched['lastfm_url']}")
                    track_obj = make_track(enriched)
                    enriched_debug.append(track_obj)
                    yield "data: " + json.dumps({"track": track_obj}) + "\n\n"
                except Exception:
                    yield "data: " + json.dumps({"track": {"error": "enrichment failed"}}) + "\n\n"
                        # --- Debug logging after enrichment ---
            try:
                with open("debug_enriched_tracks.json", "w", encoding="utf-8") as f:
                    json.dump(enriched_debug, f, ensure_ascii=False, indent=2)
                print(f"[DEBUG] Dumped {len(enriched_debug)} enriched tracks to debug_enriched_tracks.json")
            except Exception as e:
                print("[DEBUG] Failed to write debug_enriched_tracks.json:", e)
            # --- For depth > 1, recursively fetch related artists' tracks ---
            if depth > 1:
                # Helper function defined above
                try:
                    related_tracks = await fetch_related_tracks_recursive(
                        artist_name, artist_id, client, headers, depth-1, limit
                    )
                    # Deduplicate with already yielded tracks
                    existing_keys = set(unique_key(t) for t in sliced)
                    seen_keys = set(existing_keys)
                    for t in related_tracks:
                        k = unique_key(t)
                        if k in seen_keys:
                            continue
                        seen_keys.add(k)
                        try:
                            enriched = await safe_enrich(t, client)
                            yield "data: " + json.dumps({"depth_track": make_track(enriched)}) + "\n\n"
                        except Exception:
                            yield "data: " + json.dumps({"depth_track": {"error": "enrichment failed"}}) + "\n\n"
                except Exception:
                    yield "data: " + json.dumps({"depth_track": {"error": "depth recursion failed"}}) + "\n\n"

            # --- Stream recommended artists ---
            try:
                all_artists = await get_all_recommended_artists(
                    artist_name, artist_id, client, headers, LASTFM_API_KEY, SOUNDCLOUD_CLIENT_ID
                )
                enriched_artists = await asyncio.gather(
                    *[
                        enrich_artist_metadata(
                            name, client,
                            {"lastfm": LASTFM_API_KEY, "soundcloud": SOUNDCLOUD_CLIENT_ID},
                            token
                        )
                        for name in all_artists
                    ]
                )
                yield "data: " + json.dumps({"recommended_artists": enriched_artists}) + "\n\n"
            except Exception:
                yield "data: " + json.dumps({"recommended_artists": "error"}) + "\n\n"

            # --- Final signal ---
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(track), media_type="text/event-stream")

# Helper for recursive related tracks
async def fetch_related_tracks_recursive(artist_name, artist_id, client, headers, depth, limit):
    collected = []
    if depth <= 0:
        return collected
    # get related artists
    related = await get_all_recommended_artists(
        artist_name, artist_id, client, headers, LASTFM_API_KEY, SOUNDCLOUD_CLIENT_ID
    )
    for rel_name in related[:5]:
        try:
            # fetch rel artist id
            search_resp = await client.get("https://api.spotify.com/v1/search",
                headers=headers, params={"q": f'artist:"{rel_name}"', "type": "artist", "limit": 1})
            items = search_resp.json().get("artists", {}).get("items", [])
            if not items:
                continue
            rel_id = items[0]["id"]
            rel_artist_name = items[0]["name"]
            # fetch tracks
            tasks = [
                fetch_spotify_tracks_and_metadata(client, headers, rel_id, rel_artist_name, limit=limit),
                fetch_deezer_tracks(client, rel_artist_name, limit=limit),
                fetch_deezer_related_tracks(client, rel_artist_name, limit=limit),
                fetch_lastfm_tracks(client, rel_artist_name, LASTFM_API_KEY, limit=limit),
                fetch_lastfm_similar_tracks(client, rel_artist_name, "", LASTFM_API_KEY, limit=limit),
                get_soundcloud_recommendations("", rel_artist_name, client, SOUNDCLOUD_CLIENT_ID, limit=limit),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict) and "tracks" in r:
                    collected += r["tracks"]
                elif isinstance(r, list):
                    collected += r
            # recursive deeper
            deeper = await fetch_related_tracks_recursive(rel_artist_name, rel_id, client, headers, depth-1, limit)
            collected += deeper
        except Exception:
            continue
    return collected



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





