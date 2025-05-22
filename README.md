# 🎧 Music Space API

A FastAPI backend that provides music recommendations based on track or artist using **Spotify**, **Deezer**, and **Last.fm** APIs.

## 🚀 Features

- `/recommendations/by-track?track=...`
- `/recommendations/by-artist?artist=...`
- `/token` route for preview token use
- Artist enrichment with Wikipedia / Spotify fallback
- Smart deduplication & metadata merging

## 🧱 Tech Stack

- FastAPI
- httpx (async HTTP client)
- uvicorn
- dotenv
- CORS middleware

## 📦 Install

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Create .env or setup Enviroment variables

```bash
SPOTIFY_CLIENT_ID=your_spotify_id
SPOTIFY_CLIENT_SECRET=your_spotify_secret
LASTFM_API_KEY=your_lastfm_api_key
```

## CORS setup (now setup for all urls)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
CORSMiddleware,
allow_origins=["*"], # Change to your frontend URL in production
allow_methods=["*"],
allow_headers=["*"],
)
```
