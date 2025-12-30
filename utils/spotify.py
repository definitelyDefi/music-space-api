from urllib.parse import quote

async def fetch_spotify_recommended_artists(client, headers, artist_id):
    rec_artists = []
    url = f"https://api.spotify.com/v1/artists/{artist_id}/related-artists"
    resp = await client.get(url, headers=headers)

    for artist in resp.json().get("artists", [])[:10]:
        rec_artists.append({
            "name": artist["name"],
            "image_url": artist.get("images", [{}])[0].get("url"),
            "genres": artist.get("genres", []),
            "links": {
                "spotify": artist["external_urls"].get("spotify")
            },
            "source": "Spotify"
        })

    return rec_artists

async def extract_artist_info_from_spotify(client, headers, track_title, track_artist):
    query_text = f"{track_title} {track_artist}" if track_artist else track_title
    resp = await client.get("https://api.spotify.com/v1/search", headers=headers, params={"q": query_text, "type": "track", "limit": 1})
    items = resp.json().get("tracks", {}).get("items", [])
    if not items and track_artist:
        strict_q = f'track:"{track_title}" artist:"{track_artist}"'
        resp = await client.get("https://api.spotify.com/v1/search", headers=headers, params={"q": strict_q, "type": "track", "limit": 1})
        items = resp.json().get("tracks", {}).get("items", [])
    if not items:
        raise ValueError("Spotify track not found")
    return items[0]["artists"][0]["id"], items[0]["artists"][0]["name"]


async def fetch_spotify_tracks_and_metadata(client, headers, artist_id, artist_name, limit=20, offset=0):
    result = {"artist_metadata": {}, "tracks": []}

    # Fetch artist metadata
    artist_info = await client.get(f"https://api.spotify.com/v1/artists/{artist_id}", headers=headers)
    artist_json = artist_info.json()
    
    spotify_url = artist_json.get("external_urls", {}).get("spotify")

    # Optional enrichment using artist name
    deezer_url = f"https://www.deezer.com/search/{quote(artist_name)}"
    lastfm_url = f"https://www.last.fm/music/{quote(artist_name)}"
    soundcloud_url = f"https://soundcloud.com/search?q={quote(artist_name)}"

    result["artist_metadata"] = {
        "name": artist_name,
        "image_url": artist_json.get("images", [{}])[0].get("url"),
        "genres": artist_json.get("genres", []),
        "spotify_url": spotify_url,
        "deezer_url": deezer_url,
        "lastfm_url": lastfm_url,
        "soundcloud_url": soundcloud_url,
        # "official_website": extract_if_you_have  # Optional
    }

    tracks = []

    # Fetch top tracks of the main artist
    top_resp = await client.get(
        f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
        headers=headers,
        params={"market": "US"}
    )
    tracks += top_resp.json().get("tracks", [])

    # Fetch related artists and their top tracks
    rel_resp = await client.get(f"https://api.spotify.com/v1/artists/{artist_id}/related-artists", headers=headers)
    related = rel_resp.json().get("artists", [])[:10]

    for rel in related:
        rel_top = await client.get(
            f"https://api.spotify.com/v1/artists/{rel['id']}/top-tracks",
            headers=headers,
            params={"market": "US"}
        )
        tracks += rel_top.json().get("tracks", [])[:2]

    # Apply pagination manually
    paginated_tracks = tracks[offset:offset + limit]

    for t in paginated_tracks:
        result["tracks"].append({
            "title": t["name"],
            "artist": t["artists"][0]["name"],
            "duration_ms": t["duration_ms"],
            "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
            "preview_url": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "deezer_url": None,
            "soundcloud_url": None,
            "source": ["Spotify"]
        })

    return result

# api/services/spotify_recs.py
import json

SPOTIFY_GENRE_SEEDS = {
    # trimmed, but include ~100+ from docs
    "acoustic","afrobeat","alt-rock","alternative","ambient","anime","black-metal","bluegrass","blues",
    "bossanova","brazil","breakbeat","british","cantopop","chicago-house","children","chill","classical",
    "club","comedy","country","dance","dancehall","death-metal","deep-house","detroit-techno","disco",
    "disney","drum-and-bass","dub","dubstep","edm","electro","electronic","emo","folk","forro","french",
    "funk","garage","german","gospel","goth","grindcore","groove","grunge","guitar","happy-hardcore",
    "hard-rock","hardcore","hardstyle","heavy-metal","hip-hop","holidays","honky-tonk","house","idm",
    "indian","indie","indie-pop","industrial","iranian","j-dance","j-idol","j-pop","j-rock","jazz",
    "k-pop","kids","latin","latino","malay","mandopop","metal","metalcore","minimal-techno","mpb",
    "new-age","new-release","opera","pagode","party","philippines-opm","piano","pop","pop-film","power-pop",
    "progressive-house","psychedelic","punk","punk-rock","r-n-b","rainy-day","reggae","reggaeton","road-trip",
    "rock","rock-n-roll","rockabilly","romance","sad","salsa","samba","sertanejo","show-tunes","singer-songwriter",
    "ska","sleep","songwriter","soul","soundtracks","spanish","study","summer","swedish","synth-pop",
    "tango","techno","trance","trip-hop","turkish","work-out","world-music"
}

CANONICAL_MAP = {
    "hip hop": "hip-hop",
    "hiphop": "hip-hop",
    "rnb": "r-n-b",
    "r&b": "r-n-b",
    "rock n roll": "rock-n-roll",
    "workout": "work-out",
    "lofi": "chill",          # no official 'lofi' seed → closest vibes
    "lo-fi": "chill",
    "alt": "alternative",
}

MOOD_FEATURES = {
    "happy":     {"target_valence": 0.85, "target_energy": 0.75, "target_danceability": 0.7},
    "sad":       {"target_valence": 0.25, "target_energy": 0.35, "target_speechiness": 0.1},
    "chill":     {"target_energy": 0.4,  "target_danceability": 0.55, "target_instrumentalness": 0.3},
    "energetic": {"target_energy": 0.9,  "target_danceability": 0.8},
    "romantic":  {"target_valence": 0.7, "target_acousticness": 0.5},
    "dark":      {"target_valence": 0.15,"target_energy": 0.6},
}

MOOD_TO_GENRES = {
    "happy": ["dance","pop","party"],
    "sad": ["acoustic","piano","singer-songwriter"],
    "chill": ["chill","ambient","jazz","study"],
    "energetic": ["edm","dance","rock","work-out"],
    "romantic": ["soul","r-n-b","acoustic"],
    "dark": ["industrial","metal","alternative"],
}

def _normalize_tag(tag: str) -> str:
    t = tag.lower().strip()
    t = CANONICAL_MAP.get(t, t.replace(" ", "-"))
    return t

def _pick_seed_genres(tags):
    seeds = []
    for t in tags:
        n = _normalize_tag(t)
        if n in SPOTIFY_GENRE_SEEDS:
            seeds.append(n)
        elif n in MOOD_TO_GENRES:
            for g in MOOD_TO_GENRES[n]:
                if g in SPOTIFY_GENRE_SEEDS:
                    seeds.append(g)
    # uniqueness + cap at 5
    seeds = list(dict.fromkeys(seeds))[:5]
    if not seeds:
        seeds = ["pop"]
    return seeds

async def get_recommendations_by_genre_or_mood(client, tags, spotify_token, market: str = "NL"):
    """
    Robust recs: no call to /available-genre-seeds.
    - Normalize tags → valid seed_genres
    - Add mood-based audio features
    - Fallback 1: seed_artists / seed_tracks from /search
    - Fallback 2: plain /search tracks
    """
    if not tags:
        tags = ["chill"]
    headers = {"Authorization": f"Bearer {spotify_token}"}

    # 1) build seeds + features
    seed_genres = _pick_seed_genres(tags)
    features = {}
    for t in tags:
        f = MOOD_FEATURES.get(t.lower())
        if f:
            features.update(f)

    params = {
        "limit": 20,
        "seed_genres": ",".join(seed_genres),
        "market": market,
        **features,
    }

    # 2) try recommendations with genres
    recs_url = "https://api.spotify.com/v1/recommendations"
    recs_response = await client.get(recs_url, headers=headers, params=params)

    tracks, artists = [], []

    if recs_response.status_code == 200:
        data = recs_response.json()
        if data.get("tracks"):
            for item in data["tracks"]:
                tracks.append({
                    "title": item["name"],
                    "artist": item["artists"][0]["name"],
                    "spotify_url": item["external_urls"]["spotify"],
                    "cover": (item["album"]["images"][0]["url"] if item["album"].get("images") else None),
                    "preview_url": item.get("preview_url"),
                    "duration_ms": item.get("duration_ms"),
                    "source": ["Spotify Recommendations"]
                })
                for a in item.get("artists", []):
                    artists.append({"name": a["name"], "spotify_url": a["external_urls"]["spotify"], "source": ["Spotify Recommendations"]})

    # 3) Fallback: seed with artists/tracks from search if empty
    if not tracks:
        # Build seeds from search hits
        seed_artists, seed_tracks = [], []
        for tag in tags:
            q = _normalize_tag(tag).replace("-", " ")
            # top artists for tag
            a_resp = await client.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params={"q": q, "type": "artist", "limit": 3, "market": market},
            )
            a_items = a_resp.json().get("artists", {}).get("items", []) if a_resp.status_code == 200 else []
            seed_artists += [a["id"] for a in a_items[:2]]

            # top tracks for tag
            t_resp = await client.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params={"q": q, "type": "track", "limit": 4, "market": market},
            )
            t_items = t_resp.json().get("tracks", {}).get("items", []) if t_resp.status_code == 200 else []
            seed_tracks += [t["id"] for t in t_items[:3]]

        # call recommendations with mixed seeds (up to 5 total)
        mix_params = {
            "limit": 20,
            "market": market,
        }
        if seed_artists:
            mix_params["seed_artists"] = ",".join(seed_artists[:2])
        if seed_tracks:
            mix_params["seed_tracks"] = ",".join(seed_tracks[:3])
        if seed_genres:
            mix_params["seed_genres"] = ",".join(seed_genres[: max(0, 5 - (len(seed_artists[:2]) + len(seed_tracks[:3])) )])

        r2 = await client.get(recs_url, headers=headers, params=mix_params)
        if r2.status_code == 200:
            d2 = r2.json()
            for item in d2.get("tracks", []):
                tracks.append({
                    "title": item["name"],
                    "artist": item["artists"][0]["name"],
                    "spotify_url": item["external_urls"]["spotify"],
                    "cover": (item["album"]["images"][0]["url"] if item["album"].get("images") else None),
                    "preview_url": item.get("preview_url"),
                    "duration_ms": item.get("duration_ms"),
                    "source": ["Spotify Recommendations (Search-Seeded)"]
                })
                for a in item.get("artists", []):
                    artists.append({"name": a["name"], "spotify_url": a["external_urls"]["spotify"], "source": ["Spotify Recommendations (Search-Seeded)"]})

    # 4) Last fallback: plain /search tracks
    if not tracks:
        query = " ".join(tags)
        s_resp = await client.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": query, "type": "track,artist", "limit": 20, "market": market},
        )
        if s_resp.status_code == 200:
            sd = s_resp.json()
            for item in sd.get("tracks", {}).get("items", []):
                tracks.append({
                    "title": item["name"],
                    "artist": item["artists"][0]["name"],
                    "spotify_url": item["external_urls"]["spotify"],
                    "cover": (item["album"]["images"][0]["url"] if item["album"].get("images") else None),
                    "preview_url": item.get("preview_url"),
                    "duration_ms": item.get("duration_ms"),
                    "source": ["Spotify Search Fallback"]
                })
            for item in sd.get("artists", {}).get("items", []):
                artists.append({
                    "name": item["name"],
                    "spotify_url": item["external_urls"]["spotify"],
                    "image_url": (item["images"][0]["url"] if item.get("images") else None),
                    "genres": item.get("genres", []),
                    "source": ["Spotify Search Fallback"]
                })

    # Dedup artists by name
    uniq_artists = list({a["name"].lower(): a for a in artists}.values())
    return {"tracks": tracks, "artists": uniq_artists}