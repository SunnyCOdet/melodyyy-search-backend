# 🎵 Melodyyy - Music Learning Platform

A Duolingo-like platform for learning to sing. Search for any song, and the system will:
1. Download the most viewed video from YouTube
2. Separate vocals and instrumentals using Demucs
3. Transcribe lyrics with timing using Whisper
4. Extract pitch contours for singing comparison
5. Store everything in cloud (or local) storage

## Features

- 🔍 **Smart Search**: Finds the most viewed version of any song
- 🎤 **Vocal Separation**: Demucs AI separates vocals from music
- 📝 **Lyrics Extraction**: Whisper transcribes with word-level timing
- 🎼 **Pitch Analysis**: Extracts pitch contours for comparison
- ☁️ **Cloud Storage**: S3-compatible storage with local fallback
- 🎮 **Singing Practice**: Compare your singing to the original

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MELODYYY PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [User Search] ──► [YouTube] ──► [Most Viewed Video]            │
│                                        │                         │
│                                        ▼                         │
│                              [Download WAV]                      │
│                                        │                         │
│                                        ▼                         │
│                              [Demucs Separation]                 │
│                               /              \                   │
│                              ▼                ▼                  │
│                        [Vocals]         [Instrumental]           │
│                            │                  │                  │
│                            ▼                  │                  │
│                    [Whisper + Pitch]          │                  │
│                            │                  │                  │
│                            ▼                  ▼                  │
│                    ┌──────────────────────────────┐              │
│                    │      Cloud Storage (S3)      │              │
│                    │  - songs/                    │              │
│                    │  - vocals/                   │              │
│                    │  - instrumentals/            │              │
│                    │  - thumbnails/               │              │
│                    └──────────────────────────────┘              │
│                                   │                              │
│                                   ▼                              │
│                    ┌──────────────────────────────┐              │
│                    │     PostgreSQL Database      │              │
│                    │  - Music metadata            │              │
│                    │  - Cloud URLs                │              │
│                    │  - whisper_reference (JSONB) │              │
│                    └──────────────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| title | varchar(500) | Song title |
| artist | varchar(500) | Artist name |
| album | varchar(500) | Album name |
| duration | float | Duration in seconds |
| youtube_id | varchar(50) | Unique YouTube ID |
| file_path | varchar(1000) | Full mix cloud URL |
| vocal_path | varchar(1000) | Vocals only cloud URL |
| instrumental_path | varchar(1000) | Instrumentals cloud URL |
| thumbnail_url | varchar(1000) | Thumbnail URL |
| whisper_language | varchar(10) | Detected language |
| whisper_reference | JSONB | Lyrics + timing + pitch |
| processing_status | varchar(50) | pending/processing/completed/failed |
| created_at | timestamptz | Creation timestamp |

## whisper_reference Structure

```json
{
  "lines": [
    {
      "line_index": 0,
      "text": "I'm on top of the world",
      "normalized_text": "im on top of the world",
      "start_time": 12.42,
      "end_time": 15.91,
      "words": [
        { "word": "im", "start": 12.42, "end": 12.88 },
        { "word": "on", "start": 12.88, "end": 13.10 }
      ],
      "pitch": {
        "contour": [0.12, 0.18, 0.15, 0.21],
        "time_offsets": [0.0, 0.3, 0.6, 0.9],
        "variance": 0.02
      }
    }
  ]
}
```

## Prerequisites

- Python 3.10+
- PostgreSQL database
- FFmpeg
- CUDA GPU (recommended for Demucs/Whisper)

## Installation

1. **Clone the project:**
   ```bash
   cd melodyyy
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   .\venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   Edit `.env` file:
   ```env
   DATABASE_URL=postgresql://postgres:12345678@localhost:5432/postgres
   CLOUD_STORAGE_ENABLED=false
   WHISPER_MODEL=base
   DEMUCS_MODEL=htdemucs
   ```

5. **Run the application:**
   ```bash
   python -m uvicorn app.main:app --reload --port 8000
   ```

6. **Open in browser:**
   ```
   http://localhost:8000
   ```

## API Endpoints

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search?q={query}` | Search songs (YouTube + library) |
| GET | `/api/search/top?q={query}` | Get most viewed result |

### Library
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/library` | List all songs in library |
| GET | `/api/song/{youtube_id}` | Get song details |
| GET | `/api/song/{youtube_id}/lyrics` | Get lyrics + timing |
| DELETE | `/api/song/{youtube_id}` | Delete a song |

### Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/process` | Start processing a song |
| GET | `/api/process/status/{youtube_id}` | Get processing status |

### Playback
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/play/{youtube_id}` | Stream full mix |
| GET | `/api/play/{youtube_id}/vocals` | Stream vocals only |
| GET | `/api/play/{youtube_id}/instrumental` | Stream instrumental |

## Cloud Storage Setup

### AWS S3
```env
CLOUD_STORAGE_ENABLED=true
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=melodyyy-music
```

### Cloudflare R2
```env
CLOUD_STORAGE_ENABLED=true
AWS_ACCESS_KEY_ID=your_r2_key
AWS_SECRET_ACCESS_KEY=your_r2_secret
S3_BUCKET_NAME=melodyyy-music
S3_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
```

## Project Structure

```
melodyyy/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Settings from .env
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── downloader.py        # YouTube download
│   └── services/
│       ├── __init__.py
│       ├── storage.py       # Cloud/local storage
│       ├── demucs_service.py    # Audio separation
│       ├── whisper_service.py   # Transcription
│       ├── pitch_service.py     # Pitch extraction
│       └── processor.py     # Processing pipeline
├── templates/
│   └── index.html           # Frontend
├── storage/                 # Local storage (if cloud disabled)
│   ├── raw/                 # Downloaded WAV files
│   ├── songs/               # Processed full mix
│   ├── vocals/              # Separated vocals
│   ├── instrumentals/       # Separated instrumentals
│   └── thumbnails/          # Video thumbnails
├── .env                     # Environment variables
├── requirements.txt
└── README.md
```

## License

MIT License
