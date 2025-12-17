from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base


class Music(Base):
    """Model to store music metadata with separated vocals/instrumentals and whisper data."""
    __tablename__ = "music"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    artist = Column(String(500), nullable=True)
    album = Column(String(500), nullable=True)
    duration = Column(Float, nullable=True)  # Duration in seconds
    youtube_id = Column(String(50), unique=True, nullable=False)
    
    # Cloud/Local URLs for audio files
    file_path = Column(String(1000), nullable=False)  # Full mix (cloud URL or local path)
    vocal_path = Column(String(1000), nullable=True)  # Vocals only (cloud URL)
    instrumental_path = Column(String(1000), nullable=True)  # Instrumentals only (cloud URL)
    
    # Thumbnail
    thumbnail_url = Column(String(1000), nullable=True)
    
    # Whisper processed data
    whisper_language = Column(String(10), nullable=True)  # 'en', 'hi', 'ta', etc.
    whisper_reference = Column(JSONB, nullable=True)  # Full lyrics + timing + pitch data
    
    # Processing status
    processing_status = Column(String(50), default="pending")  # pending, processing, completed, failed
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "youtube_id": self.youtube_id,
            "file_path": self.file_path,
            "vocal_path": self.vocal_path,
            "instrumental_path": self.instrumental_path,
            "thumbnail_url": self.thumbnail_url,
            "whisper_language": self.whisper_language,
            "whisper_reference": self.whisper_reference,
            "processing_status": self.processing_status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
