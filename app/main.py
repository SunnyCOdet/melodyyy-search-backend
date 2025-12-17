"""
Melodyyy - Music Learning Platform Backend
A Duolingo-like platform for learning to sing.
"""

import os
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
import httpx

from app.database import engine, get_db, Base
from app.models import Music
from app.schemas import MusicResponse, SearchResult, DownloadRequest, ProcessingStatus
from app.downloader import search_youtube, get_most_viewed_video
from app.services.processor import SongProcessor
from app.services.storage import storage_service
from app.config import get_settings

settings = get_settings()

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Melodyyy",
    description="Music Learning Platform - Learn to sing like a pro!",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure storage directories exist
os.makedirs(settings.storage_dir, exist_ok=True)
os.makedirs(os.path.join(settings.storage_dir, "songs"), exist_ok=True)
os.makedirs(os.path.join(settings.storage_dir, "vocals"), exist_ok=True)
os.makedirs(os.path.join(settings.storage_dir, "instrumentals"), exist_ok=True)
os.makedirs(os.path.join(settings.storage_dir, "thumbnails"), exist_ok=True)

# Mount storage for serving local files
app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main HTML page."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ============== Search Endpoints ==============

@app.get("/api/search")
async def search(
    q: str = Query(..., description="Search query"),
    db: Session = Depends(get_db)
):
    """
    Search for music. First checks local database, then searches YouTube.
    Returns combined results with indicator if song is in library.
    Results are sorted by: 1) Name match (title contains query), 2) View count.
    """
    results = []
    query_lower = q.lower()
    
    # Search in local database first
    db_results = db.query(Music).filter(
        or_(
            Music.title.ilike(f"%{q}%"),
            Music.artist.ilike(f"%{q}%")
        )
    ).all()
    
    # Add local results
    local_youtube_ids = set()
    for music in db_results:
        results.append(SearchResult(
            title=music.title,
            artist=music.artist,
            youtube_id=music.youtube_id,
            thumbnail_url=music.thumbnail_url,
            duration=music.duration,
            in_library=True,
            processing_status=music.processing_status
        ))
        local_youtube_ids.add(music.youtube_id)
    
    # Search YouTube for more results
    youtube_results = search_youtube(q)
    
    for yt_result in youtube_results:
        if yt_result['youtube_id'] not in local_youtube_ids:
            results.append(SearchResult(
                title=yt_result['title'],
                artist=yt_result['artist'],
                youtube_id=yt_result['youtube_id'],
                thumbnail_url=yt_result['thumbnail_url'],
                duration=yt_result['duration'],
                view_count=yt_result.get('view_count'),
                in_library=False
            ))
    
    # Sort results: 1) Name match (title contains query), 2) View count
    def sort_key(result):
        title_lower = (result.title or "").lower()
        # Priority 1: Exact title match or title starts with query
        if title_lower == query_lower:
            name_score = 0
        elif title_lower.startswith(query_lower):
            name_score = 1
        elif query_lower in title_lower:
            name_score = 2
        else:
            name_score = 3
        
        # Priority 2: View count (higher is better, so negate)
        view_score = -(result.view_count or 0)
        
        # Library items get slight priority
        library_score = 0 if result.in_library else 1
        
        return (library_score, name_score, view_score)
    
    results.sort(key=sort_key)
    
    return {"results": results}


@app.get("/api/search/top")
async def search_top(
    q: str = Query(..., description="Search query"),
    db: Session = Depends(get_db)
):
    """
    Get the most viewed video for a search query.
    If already in library, returns that. Otherwise returns YouTube result.
    """
    # Check database first
    db_result = db.query(Music).filter(
        or_(
            Music.title.ilike(f"%{q}%"),
            Music.artist.ilike(f"%{q}%")
        )
    ).first()
    
    if db_result and db_result.processing_status == "completed":
        return {
            "source": "library",
            "song": MusicResponse.model_validate(db_result)
        }
    
    # Get most viewed from YouTube
    video = get_most_viewed_video(q)
    if video:
        # Check if this specific video is in library
        existing = db.query(Music).filter(Music.youtube_id == video['youtube_id']).first()
        if existing and existing.processing_status == "completed":
            return {
                "source": "library",
                "song": MusicResponse.model_validate(existing)
            }
        
        return {
            "source": "youtube",
            "video": video
        }
    
    raise HTTPException(status_code=404, detail="No results found")


# ============== Library Endpoints ==============

@app.get("/api/library")
async def get_library(db: Session = Depends(get_db)):
    """Get all songs in the local library."""
    songs = db.query(Music).order_by(Music.created_at.desc()).all()
    return {"songs": [MusicResponse.model_validate(song) for song in songs]}


@app.get("/api/song/{youtube_id}")
async def get_song(youtube_id: str, db: Session = Depends(get_db)):
    """Get song details including whisper reference."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    return MusicResponse.model_validate(music)


@app.get("/api/song/{youtube_id}/lyrics")
async def get_lyrics(youtube_id: str, db: Session = Depends(get_db)):
    """Get song lyrics and timing data from whisper_reference."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    if not music.whisper_reference:
        raise HTTPException(status_code=404, detail="Lyrics not available")
    
    return {
        "youtube_id": youtube_id,
        "language": music.whisper_language,
        "lyrics": music.whisper_reference
    }


# ============== Processing Endpoints ==============

@app.post("/api/process")
async def process_song(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Process a song: download, separate, transcribe.
    Runs in background and returns immediately with status.
    """
    query = request.query
    
    # Get most viewed video for query
    video = get_most_viewed_video(query)
    if not video:
        raise HTTPException(status_code=404, detail="No video found for query")
    
    youtube_id = video['youtube_id']
    
    # Check if already processing or completed
    existing = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    if existing:
        if existing.processing_status == "completed":
            return {
                "message": "Song already processed",
                "song": MusicResponse.model_validate(existing)
            }
        elif existing.processing_status == "processing":
            return {
                "message": "Song is currently processing",
                "youtube_id": youtube_id,
                "status": "processing"
            }
    
    # Create initial record
    if not existing:
        music = Music(
            title=video['title'],
            artist=video['artist'],
            duration=video.get('duration'),
            youtube_id=youtube_id,
            file_path="",
            thumbnail_url=video.get('thumbnail_url'),
            processing_status="pending"
        )
        db.add(music)
        db.commit()
    
    # Start background processing
    background_tasks.add_task(process_song_task, youtube_id)
    
    return {
        "message": "Processing started",
        "youtube_id": youtube_id,
        "status": "pending"
    }


def process_song_task(youtube_id: str):
    """Background task to process a song."""
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        processor = SongProcessor(db)
        processor.process_by_youtube_id(youtube_id)
    finally:
        db.close()


@app.get("/api/process/status/{youtube_id}")
async def get_processing_status(youtube_id: str, db: Session = Depends(get_db)):
    """Get the processing status of a song."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    return ProcessingStatus(
        youtube_id=youtube_id,
        status=music.processing_status,
        progress=100 if music.processing_status == "completed" else 50,
        message=f"Status: {music.processing_status}"
    )


# ============== Playback Endpoints ==============

@app.get("/api/play/{youtube_id}")
async def play_song(youtube_id: str, db: Session = Depends(get_db)):
    """Stream the full mix audio."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    return await stream_audio(music.file_path, f"{music.title}.wav")


@app.get("/api/play/{youtube_id}/vocals")
async def play_vocals(youtube_id: str, db: Session = Depends(get_db)):
    """Stream the vocals only."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    if not music.vocal_path:
        raise HTTPException(status_code=404, detail="Vocals not available")
    
    return await stream_audio(music.vocal_path, f"{music.title}_vocals.wav")


@app.get("/api/play/{youtube_id}/instrumental")
async def play_instrumental(youtube_id: str, db: Session = Depends(get_db)):
    """Stream the instrumental only."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    if not music.instrumental_path:
        raise HTTPException(status_code=404, detail="Instrumental not available")
    
    return await stream_audio(music.instrumental_path, f"{music.title}_instrumental.wav")


async def stream_audio(path: str, filename: str):
    """Stream audio from cloud or local storage."""
    if path.startswith("http"):
        # Stream from cloud
        async def generate():
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", path) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="audio/wav",
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )
    else:
        # Serve from local storage
        local_path = path.replace("/storage/", f"{settings.storage_dir}/")
        
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            local_path,
            media_type="audio/wav",
            filename=filename
        )


# ============== Delete Endpoint ==============

@app.delete("/api/song/{youtube_id}")
async def delete_song(youtube_id: str, db: Session = Depends(get_db)):
    """Delete a song from library and storage."""
    music = db.query(Music).filter(Music.youtube_id == youtube_id).first()
    
    if not music:
        raise HTTPException(status_code=404, detail="Song not found")
    
    # Delete files from storage
    if music.file_path:
        storage_service.delete_file(music.file_path)
    if music.vocal_path:
        storage_service.delete_file(music.vocal_path)
    if music.instrumental_path:
        storage_service.delete_file(music.instrumental_path)
    
    # Delete from database
    db.delete(music)
    db.commit()
    
    return {"message": "Song deleted successfully"}


# ============== Health Check ==============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "cloud_storage": settings.cloud_storage_enabled,
        "whisper_model": settings.whisper_model,
        "demucs_model": settings.demucs_model
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
