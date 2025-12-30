from collections import defaultdict

def combine_and_deduplicate_tracks(track_lists):
    merged = {}
    
    for track in track_lists:
        key = (track['title'].strip().lower(), track['artist'].strip().lower())

        if key not in merged:
            merged[key] = {
                "title": track["title"],
                "artist": track["artist"],
                "duration_ms": track.get("duration_ms") or track.get("duration_sec", 0) * 1000,
                "cover": track.get("cover"),
                "preview_url": track.get("preview_url"),
                "spotify_url": track.get("spotify_url"),
                "deezer_url": track.get("deezer_url"),
                "lastfm_url": track.get("lastfm_url"),  # NEW
                "soundcloud_url": track.get("soundcloud_url"),
                "source": set(track.get("source", [])),
                "titles": [track["title"]],
            }
        else:
            existing = merged[key]
            existing["duration_ms"] = existing["duration_ms"] or track.get("duration_ms") or track.get("duration_sec", 0) * 1000
            existing["cover"] = existing["cover"] or track.get("cover")
            existing["preview_url"] = existing["preview_url"] or track.get("preview_url")
            existing["spotify_url"] = existing["spotify_url"] or track.get("spotify_url")
            existing["deezer_url"] = existing["deezer_url"] or track.get("deezer_url")
            existing["lastfm_url"] = existing["lastfm_url"] or track.get("lastfm_url")  # NEW
            existing["soundcloud_url"] = existing["soundcloud_url"] or track.get("soundcloud_url")
            existing["source"].update(track.get("source", []))
            if track["title"] not in existing["titles"]:
                existing["titles"].append(track["title"])

    # Convert sets back to lists
    for value in merged.values():
        value["source"] = list(value["source"])

    return list(merged.values())