"""
YouTube Downloader Service
Downloads the most viewed video for a search query.
"""

import os
import yt_dlp
from typing import Optional, Dict, List
from app.config import get_settings

settings = get_settings()

DOWNLOAD_DIR = os.path.join(settings.storage_dir, "raw")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Common options to bypass YouTube restrictions
COMMON_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
    },
}


def search_youtube(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search YouTube for songs, sorted by view count.
    Returns results with the most viewed first.
    """
    ydl_opts = {
        **COMMON_OPTS,
        'extract_flat': True,
        'default_search': 'ytsearch',
    }
    
    # Search for more results to sort by views
    search_query = f"ytsearch{max_results * 2}:{query}"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            results = ydl.extract_info(search_query, download=False)
            if not results or 'entries' not in results:
                return []
            
            songs = []
            for entry in results['entries']:
                if entry:
                    songs.append({
                        'title': entry.get('title', 'Unknown'),
                        'artist': entry.get('uploader', entry.get('channel', 'Unknown')),
                        'youtube_id': entry.get('id'),
                        'thumbnail_url': entry.get('thumbnail'),
                        'duration': entry.get('duration'),
                        'view_count': entry.get('view_count', 0) or 0,
                    })
            
            # Sort by view count (most viewed first)
            songs.sort(key=lambda x: x['view_count'], reverse=True)
            
            return songs[:max_results]
            
        except Exception as e:
            print(f"Search error: {e}")
            return []


def get_most_viewed_video(query: str) -> Optional[Dict]:
    """
    Get the most viewed video for a search query.
    """
    results = search_youtube(query, max_results=1)
    if results:
        return results[0]
    return None


def get_video_info(youtube_id: str) -> Optional[Dict]:
    """
    Get detailed info for a specific video.
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    
    ydl_opts = {
        **COMMON_OPTS,
        'skip_download': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('uploader', info.get('channel', 'Unknown')),
                'album': info.get('album'),
                'duration': info.get('duration'),
                'youtube_id': youtube_id,
                'thumbnail_url': info.get('thumbnail'),
                'view_count': info.get('view_count', 0),
            }
        except Exception as e:
            print(f"Info error: {e}")
            return None


def download_audio(youtube_id: str) -> Optional[Dict]:
    """
    Download audio from YouTube as WAV file.
    
    Args:
        youtube_id: YouTube video ID
        
    Returns:
        Dict with file info or None on failure
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    output_path = os.path.join(DOWNLOAD_DIR, f"{youtube_id}.wav")
    
    # Skip if already downloaded
    if os.path.exists(output_path):
        print(f"Audio already exists: {output_path}")
        info = get_video_info(youtube_id)
        if info:
            info['file_path'] = output_path
            return info
    
    ydl_opts = {
        **COMMON_OPTS,
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, f"{youtube_id}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'retries': 3,
        'fragment_retries': 3,
        'ignoreerrors': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            print(f"Downloading: {url}")
            info = ydl.extract_info(url, download=True)
            
            return {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('uploader', info.get('channel', 'Unknown')),
                'album': info.get('album'),
                'duration': info.get('duration'),
                'youtube_id': youtube_id,
                'file_path': output_path,
                'thumbnail_url': info.get('thumbnail'),
            }
        except Exception as e:
            print(f"Download error: {e}")
            return None


def download_thumbnail(youtube_id: str, thumbnail_url: str) -> Optional[str]:
    """
    Download video thumbnail.
    
    Returns:
        Local path to thumbnail or None
    """
    if not thumbnail_url:
        return None
    
    import urllib.request
    
    thumb_dir = os.path.join(settings.storage_dir, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    
    # Determine extension
    ext = "jpg"
    if ".png" in thumbnail_url:
        ext = "png"
    elif ".webp" in thumbnail_url:
        ext = "webp"
    
    thumb_path = os.path.join(thumb_dir, f"{youtube_id}.{ext}")
    
    if os.path.exists(thumb_path):
        return thumb_path
    
    try:
        urllib.request.urlretrieve(thumbnail_url, thumb_path)
        return thumb_path
    except Exception as e:
        print(f"Thumbnail download error: {e}")
        return None


def get_file_path(youtube_id: str) -> str:
    """Get the file path for a downloaded song."""
    return os.path.join(DOWNLOAD_DIR, f"{youtube_id}.wav")


def file_exists(youtube_id: str) -> bool:
    """Check if a song file exists."""
    return os.path.exists(get_file_path(youtube_id))
