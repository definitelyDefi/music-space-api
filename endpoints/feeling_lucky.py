from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import asyncio, json, random, httpx

from utils.get_spotify_token import get_spotify_token

router = APIRouter()

def _track_key(item):
    name = (item.get("name") or "").strip().lower()
    artists = item.get("artists") or []
    artist_name = ""
    if isinstance(artists, list) and len(artists) > 0 and isinstance(artists[0], dict):
        artist_name = (artists[0].get("name") or "").strip().lower()
    return name + "||" + artist_name

def _to_track(item):
    artists = item.get("artists") or []
    artist_name = ""
    if isinstance(artists, list) and len(artists) > 0 and isinstance(artists[0], dict):
        artist_name = artists[0].get("name") or ""

    album = item.get("album") or {}
    images = album.get("images") or []
    cover_url = ""
    # pick a mid-size cover if possible
    if isinstance(images, list):
        if len(images) > 1 and isinstance(images[1], dict):
            cover_url = images[1].get("url") or ""
        elif len(images) > 0 and isinstance(images[0], dict):
            cover_url = images[0].get("url") or ""

    external_urls = item.get("external_urls") or {}
    spotify_url = external_urls.get("spotify") or ""

    return {
        "title": item.get("name") or "",
        "artist": artist_name,
        "cover_url": cover_url,
        "spotify_url": spotify_url,
        "preview_url": item.get("preview_url") or None,
        # optional extras if you want them later
        "id": item.get("id") or "",
    }

async def _spotify_search(client: httpx.AsyncClient, token: str, q: str, limit: int, offset: int):
    url = "https://api.spotify.com/v1/search"
    params = {"q": q, "type": "track", "limit": str(limit), "offset": str(offset)}
    headers = {"Authorization": "Bearer " + token}
    r = await client.get(url, params=params, headers=headers)
    if r.status_code != 200:
        return []
    data = r.json()
    tracks = data.get("tracks") or {}
    items = tracks.get("items") or []
    if not isinstance(items, list):
        return []
    return items

@router.get("/feeling-lucky")
async def feeling_lucky_stream(
    limit: int = Query(10, ge=1, le=50),
):
    async def event_generator():
        try:
            token = await get_spotify_token()
        except Exception:
            yield "data: " + json.dumps({"error": "Spotify token error"}) + "\n\n"
            yield "data: [DONE]\n\n"
            return

        yield "data: " + json.dumps({"info": {"source": "spotify", "limit": limit}}) + "\n\n"

        # Randomness knobs
        letters = "abcdefghijklmnopqrstuvwxyz"
        per_request = 50

        seen = set()
        picked = []

        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
            # Try multiple rounds until we collect enough unique tracks
            # (Spotify search result quality varies wildly depending on query)
            rounds = 0
            while len(picked) < limit and rounds < 12:
                rounds += 1

                q = random.choice(letters)
                # Spotify offset max is effectively 1000-ish for search; stay safe
                offset = random.randint(0, 950)

                try:
                    items = await _spotify_search(client, token, q, per_request, offset)
                except Exception:
                    items = []

                if len(items) == 0:
                    continue

                random.shuffle(items)

                for item in items:
                    k = _track_key(item)
                    if not k or k in seen:
                        continue
                    seen.add(k)

                    track_obj = _to_track(item)
                    # basic sanity
                    if not track_obj["title"] or not track_obj["artist"]:
                        continue

                    picked.append(track_obj)
                    yield "data: " + json.dumps({"track": track_obj}) + "\n\n"

                    if len(picked) >= limit:
                        break

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")