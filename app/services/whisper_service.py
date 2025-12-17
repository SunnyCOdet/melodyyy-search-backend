"""
Whisper Service for Lyrics Transcription
Extracts lyrics, word timings, and combines with pitch data.
"""

import os
import subprocess
import tempfile
import whisper
import numpy as np
import librosa
from typing import Optional, Dict, List, Any
from app.config import get_settings
from app.services.pitch_service import pitch_service

settings = get_settings()


class WhisperService:
    def __init__(self):
        self.model_name = settings.whisper_model
        self.model = None
        self.sr = 16000  # Whisper expects 16kHz audio
    
    def _load_model(self):
        """Lazy load Whisper model."""
        if self.model is None:
            print(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)
            print("Whisper model loaded")
    
    def _preprocess_audio(self, input_path: str) -> Optional[str]:
        """
        Convert audio to mono 16kHz WAV for Whisper.
        
        Args:
            input_path: Path to input audio file
            
        Returns:
            Path to preprocessed audio file
        """
        try:
            # Create temp file for preprocessed audio
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            # Use ffmpeg to convert
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ac", "1",  # Mono
                "-ar", "16000",  # 16kHz
                "-acodec", "pcm_s16le",
                temp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                return None
            
            return temp_path
            
        except Exception as e:
            print(f"Audio preprocessing error: {e}")
            return None
    
    def transcribe(self, vocal_path: str) -> Optional[Dict[str, Any]]:
        """
        Transcribe vocals and extract lyrics with timing and pitch.
        
        Args:
            vocal_path: Path to vocals audio file
            
        Returns:
            whisper_reference JSON with lines, words, and pitch data
        """
        if not os.path.exists(vocal_path):
            print(f"Vocal file not found: {vocal_path}")
            return None
        
        try:
            self._load_model()
            
            # Preprocess audio
            processed_path = self._preprocess_audio(vocal_path)
            if not processed_path:
                return None
            
            try:
                # Load audio for pitch extraction
                audio, sr = librosa.load(processed_path, sr=self.sr, mono=True)
                
                # Transcribe with Whisper
                print("Running Whisper transcription...")
                result = self.model.transcribe(
                    processed_path,
                    word_timestamps=True,
                    verbose=False
                )
                
                language = result.get("language", "en")
                segments = result.get("segments", [])
                
                # Build whisper_reference structure
                lines = []
                line_index = 0
                
                for segment in segments:
                    text = segment.get("text", "").strip()
                    if not text:
                        continue
                    
                    start_time = segment.get("start", 0)
                    end_time = segment.get("end", 0)
                    words_data = segment.get("words", [])
                    
                    # Build word timings
                    words = []
                    for word_info in words_data:
                        word_text = word_info.get("word", "").strip()
                        if word_text:
                            words.append({
                                "word": pitch_service.normalize_text(word_text),
                                "start": round(word_info.get("start", 0), 2),
                                "end": round(word_info.get("end", 0), 2)
                            })
                    
                    # Extract pitch contour for this line
                    pitch_data = pitch_service.extract_pitch_contour(
                        audio,
                        start_time,
                        end_time,
                        num_points=20
                    )
                    
                    lines.append({
                        "line_index": line_index,
                        "text": text,
                        "normalized_text": pitch_service.normalize_text(text),
                        "start_time": round(start_time, 2),
                        "end_time": round(end_time, 2),
                        "words": words,
                        "pitch": pitch_data
                    })
                    
                    line_index += 1
                
                whisper_reference = {
                    "lines": lines
                }
                
                print(f"Transcription complete: {len(lines)} lines, language={language}")
                
                return {
                    "language": language,
                    "reference": whisper_reference
                }
                
            finally:
                # Cleanup temp file
                if os.path.exists(processed_path):
                    os.remove(processed_path)
                    
        except Exception as e:
            print(f"Whisper transcription error: {e}")
            import traceback
            traceback.print_exc()
            return None


# Singleton instance
whisper_service = WhisperService()
