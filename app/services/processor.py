"""
Song Processing Pipeline
Orchestrates the full flow: download -> demucs -> whisper -> store
"""

import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import Music
from app.downloader import download_audio, get_most_viewed_video, download_thumbnail
from app.services.storage import storage_service
from app.services.demucs_service import demucs_service
from app.services.whisper_service import whisper_service
from app.config import get_settings

settings = get_settings()


class SongProcessor:
    """
    Processes songs through the full pipeline:
    1. Search for most viewed video
    2. Download audio as WAV
    3. Separate vocals and instrumentals (Demucs)
    4. Transcribe vocals (Whisper)
    5. Extract pitch contours
    6. Upload to cloud storage
    7. Store metadata in database
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.status_callbacks = []
    
    def on_status_update(self, callback):
        """Register a callback for status updates."""
        self.status_callbacks.append(callback)
    
    def _update_status(self, youtube_id: str, status: str, progress: int, message: str = ""):
        """Update processing status."""
        for callback in self.status_callbacks:
            callback(youtube_id, status, progress, message)
        
        # Also update database
        music = self.db.query(Music).filter(Music.youtube_id == youtube_id).first()
        if music:
            music.processing_status = status
            self.db.commit()
    
    def process_by_query(self, query: str) -> Optional[Music]:
        """
        Process a song by search query.
        Finds the most viewed video and processes it.
        """
        # Search for most viewed video
        video = get_most_viewed_video(query)
        if not video:
            print(f"No video found for query: {query}")
            return None
        
        return self.process_by_youtube_id(video['youtube_id'])
    
    def process_by_youtube_id(self, youtube_id: str) -> Optional[Music]:
        """
        Process a song by YouTube ID.
        
        Args:
            youtube_id: YouTube video ID
            
        Returns:
            Music model instance or None on failure
        """
        # Check if already exists and fully processed
        existing = self.db.query(Music).filter(Music.youtube_id == youtube_id).first()
        if existing and existing.processing_status == "completed":
            print(f"Song already processed: {youtube_id}")
            return existing
        
        try:
            # Step 1: Download audio
            self._update_status(youtube_id, "downloading", 10, "Downloading audio...")
            
            download_result = download_audio(youtube_id)
            if not download_result:
                self._update_status(youtube_id, "failed", 0, "Failed to download audio")
                return None
            
            raw_audio_path = download_result['file_path']
            
            # Download thumbnail
            thumb_local = download_thumbnail(youtube_id, download_result.get('thumbnail_url'))
            
            # Step 2: Create or update database record
            if existing:
                music = existing
                music.title = download_result['title']
                music.artist = download_result['artist']
                music.album = download_result.get('album')
                music.duration = download_result.get('duration')
                music.thumbnail_url = download_result.get('thumbnail_url')
            else:
                music = Music(
                    title=download_result['title'],
                    artist=download_result['artist'],
                    album=download_result.get('album'),
                    duration=download_result.get('duration'),
                    youtube_id=youtube_id,
                    file_path="",  # Will be updated after upload
                    thumbnail_url=download_result.get('thumbnail_url'),
                    processing_status="processing"
                )
                self.db.add(music)
            
            self.db.commit()
            self.db.refresh(music)
            
            # Step 3: Separate vocals and instrumentals
            self._update_status(youtube_id, "separating", 30, "Separating vocals and instrumentals...")
            
            vocals_path, instrumental_path = demucs_service.separate(raw_audio_path, youtube_id)
            
            if not vocals_path or not instrumental_path:
                self._update_status(youtube_id, "failed", 0, "Failed to separate audio")
                return None
            
            # Step 4: Upload files to storage
            self._update_status(youtube_id, "uploading", 50, "Uploading to storage...")
            
            # Upload full mix
            file_url = storage_service.upload_file(
                raw_audio_path,
                f"{youtube_id}.wav",
                subfolder="songs"
            )
            
            # Upload vocals
            vocal_url = storage_service.upload_file(
                vocals_path,
                f"{youtube_id}_vocals.wav",
                subfolder="vocals"
            )
            
            # Upload instrumentals
            instrumental_url = storage_service.upload_file(
                instrumental_path,
                f"{youtube_id}_instrumental.wav",
                subfolder="instrumentals"
            )
            
            # Upload thumbnail if downloaded
            if thumb_local:
                thumb_ext = os.path.splitext(thumb_local)[1]
                storage_service.upload_file(
                    thumb_local,
                    f"{youtube_id}{thumb_ext}",
                    subfolder="thumbnails"
                )
            
            # Update database with URLs
            music.file_path = file_url
            music.vocal_path = vocal_url
            music.instrumental_path = instrumental_url
            self.db.commit()
            
            # Step 5: Transcribe vocals with Whisper
            self._update_status(youtube_id, "transcribing", 70, "Transcribing lyrics...")
            
            whisper_result = whisper_service.transcribe(vocals_path)
            
            if whisper_result:
                music.whisper_language = whisper_result['language']
                music.whisper_reference = whisper_result['reference']
                self.db.commit()
            else:
                print(f"Whisper transcription failed for {youtube_id}, continuing anyway")
            
            # Step 6: Mark as completed
            self._update_status(youtube_id, "completed", 100, "Processing complete!")
            music.processing_status = "completed"
            self.db.commit()
            self.db.refresh(music)
            
            print(f"Song processed successfully: {music.title}")
            return music
            
        except Exception as e:
            print(f"Processing error: {e}")
            import traceback
            traceback.print_exc()
            self._update_status(youtube_id, "failed", 0, str(e))
            return None
    
    def get_or_process(self, query: str) -> Optional[Music]:
        """
        Get a song from database or process it if not available.
        
        Args:
            query: Search query
            
        Returns:
            Music model instance or None
        """
        # First, search for most viewed to get youtube_id
        video = get_most_viewed_video(query)
        if not video:
            return None
        
        youtube_id = video['youtube_id']
        
        # Check if already in database and completed
        existing = self.db.query(Music).filter(Music.youtube_id == youtube_id).first()
        if existing and existing.processing_status == "completed":
            return existing
        
        # Process the song
        return self.process_by_youtube_id(youtube_id)
