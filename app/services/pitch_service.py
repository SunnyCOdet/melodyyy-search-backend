"""
Pitch Extraction Service
Extracts pitch contour from audio for singing comparison.
Uses librosa for pitch detection.
"""

import numpy as np
import librosa
from typing import List, Dict, Optional, Tuple
import re


class PitchService:
    def __init__(self, sr: int = 16000, hop_length: int = 512):
        """
        Initialize pitch service.
        
        Args:
            sr: Sample rate (16kHz for Whisper compatibility)
            hop_length: Hop length for pitch extraction
        """
        self.sr = sr
        self.hop_length = hop_length
        self.frame_duration = hop_length / sr  # Time per frame
    
    def extract_pitch_contour(
        self,
        audio: np.ndarray,
        start_time: float,
        end_time: float,
        num_points: int = 20
    ) -> Dict:
        """
        Extract pitch contour for a segment of audio.
        
        Args:
            audio: Audio samples (mono, 16kHz)
            start_time: Start time in seconds
            end_time: End time in seconds
            num_points: Number of pitch points to extract
            
        Returns:
            Dict with contour, time_offsets, and variance
        """
        # Convert times to sample indices
        start_sample = int(start_time * self.sr)
        end_sample = int(end_time * self.sr)
        
        # Ensure valid range
        start_sample = max(0, start_sample)
        end_sample = min(len(audio), end_sample)
        
        if end_sample <= start_sample:
            return {
                "contour": [],
                "time_offsets": [],
                "variance": 0.0
            }
        
        # Extract segment
        segment = audio[start_sample:end_sample]
        
        if len(segment) < self.hop_length:
            return {
                "contour": [],
                "time_offsets": [],
                "variance": 0.0
            }
        
        try:
            # Extract pitch using pyin (probabilistic YIN)
            f0, voiced_flag, voiced_probs = librosa.pyin(
                segment.astype(float),
                fmin=librosa.note_to_hz('C2'),
                fmax=librosa.note_to_hz('C7'),
                sr=self.sr,
                hop_length=self.hop_length
            )
            
            # Filter to voiced frames only and convert to cents (relative to A4=440Hz)
            valid_pitches = []
            valid_times = []
            
            for i, (pitch, voiced) in enumerate(zip(f0, voiced_flag)):
                if voiced and not np.isnan(pitch) and pitch > 0:
                    # Convert Hz to normalized pitch (0-1 range based on vocal range)
                    # Using cents relative to C2 (65.41 Hz)
                    cents = 1200 * np.log2(pitch / 65.41) / 4800  # Normalize to 0-1 over 4 octaves
                    cents = max(0, min(1, cents))
                    valid_pitches.append(round(cents, 3))
                    valid_times.append(round(i * self.frame_duration, 3))
            
            if len(valid_pitches) == 0:
                return {
                    "contour": [],
                    "time_offsets": [],
                    "variance": 0.0
                }
            
            # Resample to fixed number of points if needed
            if len(valid_pitches) > num_points:
                indices = np.linspace(0, len(valid_pitches) - 1, num_points, dtype=int)
                valid_pitches = [valid_pitches[i] for i in indices]
                valid_times = [valid_times[i] for i in indices]
            
            # Calculate variance
            variance = round(float(np.var(valid_pitches)), 4) if len(valid_pitches) > 1 else 0.0
            
            return {
                "contour": valid_pitches,
                "time_offsets": valid_times,
                "variance": variance
            }
            
        except Exception as e:
            print(f"Pitch extraction error: {e}")
            return {
                "contour": [],
                "time_offsets": [],
                "variance": 0.0
            }
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison (lowercase, remove punctuation)."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# Singleton instance
pitch_service = PitchService()
