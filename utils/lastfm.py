
async def fetch_lastfm_recommended_artists(client, artist_name, api_key):
    rec_artists = []

    resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": api_key,
        "format": "json",
        "limit": 10
    })

    for a in resp.json().get("similarartists", {}).get("artist", []):
        rec_artists.append({
            "name": a["name"],
            "image_url": a.get("image", [{}])[-1].get("#text") if a.get("image") else None,
            "genres": [],
            "links": {
                "lastfm": a.get("url")
            },
            "source": "Last.fm"
        })

    return rec_artists

async def fetch_lastfm_tracks(client, artist_name: str, api_key: str, limit: int = 20, offset: int = 0):
    tracks = []

    # Step 1: Get similar artists
    similar_resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": api_key,
        "format": "json",
        "limit": 50  # Get more for local slicing
    })
    similar_artists = similar_resp.json().get("similarartists", {}).get("artist", [])

    all_related_tracks = []

    # Step 2: Fetch top track of each similar artist
    for artist in similar_artists:
        top_resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
            "method": "artist.gettoptracks",
            "artist": artist["name"],
            "api_key": api_key,
            "format": "json",
            "limit": 1
        })
        top_tracks = top_resp.json().get("toptracks", {}).get("track", [])
        if top_tracks:
            t = top_tracks[0]
            all_related_tracks.append({
                "title": t["name"],
                "artist": artist["name"],
                "duration_sec": int(t.get("duration", 0)),
                "cover": t["image"][-1]["#text"] if t.get("image") else None,
                "preview_url": None,
                "spotify_url": None,
                "deezer_url": t.get("url"),
                "soundcloud_url": None,
                "source": ["Last.fm"]
            })

    # Step 3: Manual pagination
    paginated = all_related_tracks[offset:offset + limit]
    tracks.extend(paginated)

    return tracks


async def fetch_lastfm_similar_tracks(client, artist_name: str, track_title: str, api_key: str, limit: int = 20):
    tracks = []
    resp = await client.get("http://ws.audioscrobbler.com/2.0/", params={
        "method": "track.getsimilar",
        "artist": artist_name,
        "track": track_title,
        "api_key": api_key,
        "format": "json",
        "limit": limit
    })
    similar = resp.json().get("similartracks", {}).get("track", [])

    for t in similar:
        tracks.append({
            "title": t["name"],
            "artist": t["artist"]["name"],
            "duration_sec": 0,
            "cover": t.get("image", [{}])[-1].get("#text"),
            "preview_url": None,
            "spotify_url": None,
            "deezer_url": None,
            "soundcloud_url": None,
            "source": ["Last.fm"]
        })

    return tracks


async def get_lastfm_tracks_and_artists_by_tag(client, tags, api_key):
 
    tracks = []
    artists = []

    for tag in tags:
        track_url = f"http://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag={tag}&api_key={api_key}&format=json&limit=10"
        artist_url = f"http://ws.audioscrobbler.com/2.0/?method=tag.gettopartists&tag={tag}&api_key={api_key}&format=json&limit=10"

        track_res = await client.get(track_url)
        artist_res = await client.get(artist_url)

        track_data = track_res.json()
        artist_data = artist_res.json()

        for t in track_data.get("tracks", {}).get("track", []):
            tracks.append({
                "title": t["name"],
                "artist": t["artist"]["name"],
                "lastfm_url": t["url"]
            })

        for a in artist_data.get("topartists", {}).get("artist", []):
            artists.append({
                "name": a["name"],
                "lastfm_url": a["url"],
                "image_url": a["image"][2]["#text"] if a["image"] else None
            })

    return {"tracks": tracks, "artists": artists}