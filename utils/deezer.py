async def fetch_deezer_recommended_artists(client, artist_name):
    rec_artists = []

    search = await client.get("https://api.deezer.com/search/artist", params={"q": artist_name})
    data = search.json().get("data", [])
    if not data:
        return rec_artists

    artist_id = data[0].get("id")
    related = await client.get(f"https://api.deezer.com/artist/{artist_id}/related")

    for a in related.json().get("data", [])[:10]:
        rec_artists.append({
            "name": a["name"],
            "image_url": a.get("picture_xl") or a.get("picture"),
            "genres": [],  # Deezer API does not include genre here
            "links": {
                "deezer": a.get("link")
            },
            "source": "Deezer"
        })

    return rec_artists


async def fetch_deezer_tracks(client, artist_name: str, limit: int = 20, offset: int = 0):
    tracks = []

    # Step 1: Search for artist by name
    d_search = await client.get(f"https://api.deezer.com/search/artist", params={"q": artist_name})
    data = d_search.json().get("data", [])

    if not data:
        return tracks

    artist_id = data[0]["id"]

    # Step 2: Fetch top tracks of the artist
    top = await client.get(f"https://api.deezer.com/artist/{artist_id}/top", params={"limit": 100})
    all_tracks = top.json().get("data", [])

    # Step 3: Manual pagination
    paginated = all_tracks[offset:offset + limit]

    for t in paginated:
        tracks.append({
            "title": t["title"],
            "artist": t["artist"]["name"],
            "duration_sec": t["duration"],
            "cover": t["album"]["cover_big"],
            "preview_url": t.get("preview"),
            "spotify_url": None,
            "deezer_url": t["link"],
            "soundcloud_url": None,
            "source": ["Deezer"]
        })

    return tracks


async def fetch_deezer_related_tracks(client, artist_name: str, limit: int = 20, offset: int = 0):
    tracks = []

    # Step 1: Find artist ID
    search_resp = await client.get("https://api.deezer.com/search/artist", params={"q": artist_name})
    artists = search_resp.json().get("data", [])
    if not artists:
        return tracks

    artist_id = artists[0]["id"]

    # Step 2: Get related artists
    related_resp = await client.get(f"https://api.deezer.com/artist/{artist_id}/related")
    related_artists = related_resp.json().get("data", [])

    all_related_tracks = []

    # Step 3: For each related artist, get their top tracks
    for related in related_artists[:10]:  # limit number of related artists to reduce API load
        rel_id = related["id"]
        top_resp = await client.get(f"https://api.deezer.com/artist/{rel_id}/top", params={"limit": 3})
        for t in top_resp.json().get("data", []):
            all_related_tracks.append({
                "title": t["title"],
                "artist": t["artist"]["name"],
                "duration_sec": t["duration"],
                "cover": t["album"]["cover_big"],
                "preview_url": t.get("preview"),
                "spotify_url": None,
                "deezer_url": t["link"],
                "soundcloud_url": None,
                "source": ["Deezer"]
            })

    # Step 4: Manual pagination
    paginated = all_related_tracks[offset:offset + limit]
    tracks.extend(paginated)

    return tracks


import random
import asyncio

# Mapping of common tags to Deezer genre IDs
DEEZE_GENRE_MAP = {
    "pop": 132,
    "rock": 152,
    "electronic": 106,
    "hip hop": 116,
    "hip-hop": 116,
    "r&b": 165,
    "r-n-b": 165,
    "jazz": 129,
    "classical": 98,
    "dance": 113,
    "reggae": 144,
    "soul": 197,
    "metal": 464,
    "ambient": 464,  # ambient doesn't exist directly; use "metal" or "electronic" fallback
    "chill": 106,    # treat "chill" as electronic
}

# Optional mood → filtering keywords
MOOD_KEYWORDS = {
    "happy": ["summer", "party", "sunshine"],
    "sad": ["melancholy", "sad", "emotional"],
    "chill": ["relax", "lofi", "smooth"],
    "energetic": ["workout", "club", "dance"],
    "romantic": ["love", "soft", "ballad"],
    "dark": ["dark", "goth", "moody"]
}


async def get_deezer_tracks_and_artists_by_genre(client, tags):
    """
    Smarter Deezer fetcher — uses genre IDs + mood-based searches.
    """
    tracks = []
    artists = []

    # Split tags into mood and genre
    moods = [t for t in tags if t.lower() in MOOD_KEYWORDS]
    genres = [t for t in tags if t.lower() in DEEZE_GENRE_MAP]

    # Default fallback
    if not genres:
        genres = ["pop"]

    # Pick up to 2 genres randomly to mix results
    genres = random.sample(genres, min(len(genres), 2))

    for genre in genres:
        genre_id = DEEZE_GENRE_MAP.get(genre.lower())

        # Try to get top artists for that genre
        try:
            artist_resp = await client.get(f"https://api.deezer.com/genre/{genre_id}/artists")
            artist_data = artist_resp.json().get("data", [])
            for a in artist_data[:10]:
                artists.append({
                    "name": a["name"],
                    "deezer_url": a["link"],
                    "image_url": a.get("picture_medium"),
                    "source": ["Deezer"]
                })
        except Exception as e:
            print(f"[Deezer] Artist fetch failed for {genre}: {e}")

        # Try to fetch tracks via radios for that genre (works like mood playlists)
        try:
            radios_resp = await client.get(f"https://api.deezer.com/genre/{genre_id}/radios")
            radios = radios_resp.json().get("data", [])
            if radios:
                random_radio = random.choice(radios)
                tracks_resp = await client.get(f"https://api.deezer.com/radio/{random_radio['id']}/tracks")
                data = tracks_resp.json().get("data", [])
                for item in data:
                    tracks.append({
                        "title": item["title"],
                        "artist": item["artist"]["name"],
                        "deezer_url": item["link"],
                        "cover": item["album"]["cover_medium"],
                        "source": ["Deezer Radio"]
                    })
        except Exception as e:
            print(f"[Deezer] Radio fetch failed for {genre}: {e}")

        # If no tracks found, fall back to mood keyword search
        if not tracks:
            keywords = MOOD_KEYWORDS.get(random.choice(moods), ["mix", "hits"]) if moods else ["mix", "hits"]
            for keyword in keywords:
                search_q = f"{genre} {keyword}"
                res = await client.get(f"https://api.deezer.com/search", params={"q": search_q})
                data = res.json().get("data", [])
                for item in data[:10]:
                    tracks.append({
                        "title": item["title"],
                        "artist": item["artist"]["name"],
                        "deezer_url": item["link"],
                        "cover": item["album"]["cover_medium"],
                        "source": ["Deezer Search"]
                    })

    # Deduplicate by title + artist
    seen = set()
    unique_tracks = []
    for t in tracks:
        key = (t["title"].lower(), t["artist"].lower())
        if key not in seen:
            seen.add(key)
            unique_tracks.append(t)

    unique_artists = {a["name"].lower(): a for a in artists}.values()

    return {"tracks": unique_tracks, "artists": list(unique_artists)}