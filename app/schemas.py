from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class PitchData(BaseModel):
    contour: List[float]
    time_offsets: List[float]
    variance: float


class LyricLine(BaseModel):
    line_index: int
    text: str
    normalized_text: str
    start_time: float
    end_time: float
    words: List[WordTiming]
    pitch: PitchData


class WhisperReference(BaseModel):
    lines: List[LyricLine]


class MusicBase(BaseModel):
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[float] = None
    youtube_id: str
    thumbnail_url: Optional[str] = None


class MusicCreate(MusicBase):
    file_path: str


class MusicResponse(MusicBase):
    id: int
    file_path: str
    vocal_path: Optional[str] = None
    instrumental_path: Optional[str] = None
    whisper_language: Optional[str] = None
    whisper_reference: Optional[Any] = None
    processing_status: str = "pending"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    title: str
    artist: Optional[str] = None
    youtube_id: str
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    view_count: Optional[int] = None
    in_library: bool = False
    processing_status: Optional[str] = None


class DownloadRequest(BaseModel):
    query: str  # Search query - will find most viewed video


class ProcessingStatus(BaseModel):
    youtube_id: str
    status: str  # pending, downloading, separating, transcribing, completed, failed
    progress: int  # 0-100
    message: Optional[str] = None
