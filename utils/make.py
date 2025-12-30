def make_track(t):
    return {
            "title": t.get("title", "").strip(),
            "artist": t.get("artist", "").strip(),
            "duration_ms": (
                t.get("duration_ms")
                or (t.get("duration_sec", 0) * 1000 if isinstance(t.get("duration_sec"), (int, float)) else 0)
            ),
            "cover_url": t.get("cover_url") or t.get("cover") or "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png",
            "preview_url": t.get("preview_url"),
            "spotify_url": t.get("spotify_url"),
            "deezer_url": t.get("deezer_url"),
            "lastfm_url": t.get("lastfm_url"),
            "soundcloud_url": t.get("soundcloud_url"),
            "source": t.get("source", []),

            # Enrichment-related fields
            "genre": t.get("genre", []),
            "style": t.get("style", []),
            "year": t.get("year"),
            "label": t.get("label", []),
            "format": t.get("format", []),
        }