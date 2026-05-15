# Verbatone

Verbatone is a local-first Flask + React music player with importable audio,
synced lyrics, TTML serving, and a browser player.

## Run the dev app

Backend:

```bash
cd backend
../.venv311/bin/python -m pip install -r requirements.txt
VERBATONE_BACKEND_PORT=5051 ../.venv311/bin/python app.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL and choose files or a folder containing audio files.

The frontend proxies `/api` to `http://127.0.0.1:5051` by default. Override it with
`VITE_BACKEND_URL` if needed.

## Notes

- Local audio files, generated TTML, cover art, and the SQLite database live under
  `backend/data/` and are intentionally not committed.
- Lyrics can be generated with provider keys or pasted manually, then synced.
- Genius lyrics fetching needs a Client Access Token. A Client ID or Client
  Secret will be rejected by the API.
- Existing synced lyrics should be regenerated after lyric-format changes to get
  the newest line preservation and smoother karaoke rendering.
