async def fetch_soundcloud_recommended_artists(client, artist_name, client_id):
    try:
        response = await client.get(
            "https://api-v2.soundcloud.com/search/users",
            params={"q": artist_name, "client_id": client_id, "limit": 1}
        )
        if response.status_code != 200:
            print(f"[SoundCloud ERROR {response.status_code}]:", response.text)
            return []

        data = response.json()
        if not data or "collection" not in data or not data["collection"]:
            print("[SoundCloud] No artist found")
            return []

        user_id = data["collection"][0]["id"]

        related = await client.get(
            f"https://api-v2.soundcloud.com/users/{user_id}/related",
            params={"client_id": client_id, "limit": 10}
        )

        if related.status_code != 200:
            print(f"[SoundCloud Related ERROR {related.status_code}]:", related.text)
            return []

        try:
            related_data = related.json()
        except Exception as e:
            print("[SoundCloud JSON ERROR]:", e, related.text)
            return []

        return related_data.get("collection", [])

    except Exception as e:
        print("[SoundCloud Fetch ERROR]:", e)
        return []

async def get_soundcloud_recommendations(track_title, artist_name, client, soundcloud_client_id, offset=0, limit=10):
    soundcloud_tracks = []
    seen = set()

    # Step 1: Search for the given track
    try:
        query = f"{track_title} {artist_name}" if artist_name else track_title
        sc_track_search = await client.get(
            "https://api-v2.soundcloud.com/search/tracks",
            params={
                "q": query,
                "client_id": soundcloud_client_id,
                "limit": limit,
                "offset": offset
            }
        )
        for t in sc_track_search.json().get("collection", []):
            key = (t["title"].strip().lower(), t["user"]["username"].strip().lower())
            if key not in seen:
                seen.add(key)
                soundcloud_tracks.append({
                    "title": t["title"],
                    "artist": t["user"]["username"],
                    "duration_ms": t["duration"],
                    "cover": t.get("artwork_url"),
                    "preview_url": t.get("permalink_url"),
                    "spotify_url": None,
                    "deezer_url": None,
                    "soundcloud_url": t.get("permalink_url"),
                    "source": ["SoundCloud"]
                })
    except Exception as e:
        print("[SoundCloud Search Error]:", e)

    # Step 2: Artist tracks + related artists
    try:
        if not artist_name:
            return soundcloud_tracks

        # Find artist ID
        artist_search = await client.get(
            "https://api-v2.soundcloud.com/search/users",
            params={"q": artist_name, "client_id": soundcloud_client_id, "limit": 1}
        )
        artist_result = artist_search.json().get("collection", [])
        if not artist_result:
            return soundcloud_tracks

        artist_id = artist_result[0]["id"]

        # Artist top tracks
        artist_tracks_resp = await client.get(
            f"https://api-v2.soundcloud.com/users/{artist_id}/tracks",
            params={"client_id": soundcloud_client_id, "limit": limit, "offset": offset}
        )
        for t in artist_tracks_resp.json().get("collection", []):
            key = (t["title"].strip().lower(), artist_name.lower())
            if key not in seen:
                seen.add(key)
                soundcloud_tracks.append({
                    "title": t["title"],
                    "artist": artist_name,
                    "duration_ms": t["duration"],
                    "cover": t.get("artwork_url"),
                    "preview_url": t.get("permalink_url"),
                    "spotify_url": None,
                    "deezer_url": None,
                    "soundcloud_url": t.get("permalink_url"),
                    "source": ["SoundCloud"]
                })

        # Related artists' tracks
        rel_artists = await client.get(
            f"https://api-v2.soundcloud.com/users/{artist_id}/recommendations",
            params={"client_id": soundcloud_client_id, "limit": 5}
        )
        for rel in rel_artists.json().get("collection", []):
            if rel.get("kind") != "user":
                continue
            rel_tracks_resp = await client.get(
                f"https://api-v2.soundcloud.com/users/{rel['id']}/tracks",
                params={"client_id": soundcloud_client_id, "limit": 2, "offset": offset}
            )
            for t in rel_tracks_resp.json().get("collection", []):
                key = (t["title"].strip().lower(), rel["username"].strip().lower())
                if key not in seen:
                    seen.add(key)
                    soundcloud_tracks.append({
                        "title": t["title"],
                        "artist": rel["username"],
                        "duration_ms": t["duration"],
                        "cover": t.get("artwork_url"),
                        "preview_url": t.get("permalink_url"),
                        "spotify_url": None,
                        "deezer_url": None,
                        "soundcloud_url": t.get("permalink_url"),
                        "source": ["SoundCloud"]
                    })

    except Exception as e:
        print("[SoundCloud Artist/Related Error]:", e)

    return soundcloud_tracks



async def get_soundcloud_tracks_and_artists_by_tag(client, tags, client_id):
    tracks = []
    artists = []

    for tag in tags:
        url = f"https://api-v2.soundcloud.com/search/tracks?q={tag}&client_id={client_id}&limit=10"
        res = await client.get(url)
        data = res.json()

        for item in data.get("collection", []):
            tracks.append({
                "title": item["title"],
                "artist": item["user"]["username"],
                "soundcloud_url": item["permalink_url"]
            })
            artists.append({
                "name": item["user"]["username"],
                "soundcloud_url": item["user"]["permalink_url"],
                "image_url": item["user"].get("avatar_url")
            })

    return {"tracks": tracks, "artists": artists}