# Whisper Proxy Demo

A two-part project combining a FastAPI backend that proxies Whisper API requests with Firebase authentication and a Flutter client for uploading audio, converting via FFmpeg, and polling transcription status.

## Backend

### Prerequisites
- Python 3.11
- Firebase project configured for authentication
- Whisper API key (`sk-live-example-1234567890` stored in backend `.env`)

### Environment
Copy `.env.example` to `.env` and adjust as needed. Key variables:

```
WHISPER_API_KEY=sk-live-example-1234567890
FIREBASE_PROJECT_ID=demo-whisper-th
LIMITER_BACKEND=memory
```

### Install & Run (development)

```
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### Run with Docker

```
cd backend
docker compose up --build
```

### API Overview
- `POST /v1/transcribe` — Upload audio (multipart) with Firebase ID Token in `Authorization` header.
- `GET /v1/status/{task_id}` — Poll transcription job status.
- `GET /v1/me/usage` — View quota usage and configured limits.

### Testing

```
pytest -q backend/tests
```

## Flutter Client

### Prerequisites
- Flutter SDK (3.16 or newer)
- Firebase project setup with `google-services.json`/`GoogleService-Info.plist`
- Whisper proxy backend reachable at `https://api.example-th.dev`

Update `flutter_app/lib/services/api_client.dart` if your backend URL differs.

### Run

```
cd flutter_app
flutter pub get
flutter run
```

### Flow
1. Pick an audio/video file.
2. Client converts the media to mono 16 kHz WAV using `ffmpeg_kit_flutter_min_gpl`.
3. Uploads to backend with Firebase ID Token.
4. Polls job status and displays transcript upon completion.

## Firebase Setup Notes
- Enable Email/Password or another provider.
- Ensure the Flutter app is registered with Firebase and includes proper configuration files per platform.
- Users must be signed in before calling the API to obtain a valid ID token.

## Usage Limits
Default limits (override via environment):
- `MAX_FILE_MB=200`
- `MAX_CLIP_MIN=90`
- `RPM_PER_USER=30`
- `RPM_PER_TENANT=120`
- `CONCURRENT_USER=1`
- `CONCURRENT_TENANT=5`
- `MINUTES_PER_DAY=60`
- `MINUTES_PER_MONTH=1200`
- `DEFAULT_MODEL=large-v3`
- `ALLOW_DIARIZATION=false`

## Whisper API
The backend proxies to `https://api.whisper-api.com` with `X-API-Key` header configured from environment variables. Ensure network access and quota with Whisper API provider.
