"""
Demucs Music Source Separation Service
Separates audio into vocals and instrumentals.
Uses Python API directly with librosa for audio loading.
"""

import os
import torch
import numpy as np
import soundfile as sf
import librosa
from typing import Optional, Tuple
from app.config import get_settings

settings = get_settings()


class DemucsService:
    def __init__(self):
        self.model_name = settings.demucs_model
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Demucs will use device: {self.device}")
    
    def _load_model(self):
        """Lazy load Demucs model."""
        if self.model is None:
            print(f"Loading Demucs model: {self.model_name}")
            from demucs.pretrained import get_model
            from demucs.apply import BagOfModels
            
            self.model = get_model(self.model_name)
            if isinstance(self.model, BagOfModels):
                self.model = self.model.models[0]
            self.model.to(self.device)
            self.model.eval()
            print(f"Demucs model loaded on {self.device}")
    
    def separate(self, input_path: str, youtube_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Separate audio into vocals and instrumentals.
        
        Args:
            input_path: Path to the input audio file (WAV)
            youtube_id: Unique identifier for naming output files
            
        Returns:
            Tuple of (vocals_path, instrumentals_path) or (None, None) on failure
        """
        if not os.path.exists(input_path):
            print(f"Input file not found: {input_path}")
            return None, None
        
        try:
            self._load_model()
            
            from demucs.apply import apply_model
            
            # Get model sample rate
            model_sr = self.model.samplerate
            
            # Load audio using librosa (no FFmpeg needed)
            print(f"Loading audio with librosa: {input_path}")
            audio, sr = librosa.load(input_path, sr=model_sr, mono=False)
            
            # Handle mono/stereo
            if audio.ndim == 1:
                # Mono - duplicate to stereo
                audio = np.stack([audio, audio], axis=0)
            elif audio.shape[0] > 2:
                # More than 2 channels, take first 2
                audio = audio[:2]
            
            print(f"Audio loaded: shape={audio.shape}, sr={model_sr}")
            
            # Convert to torch tensor and add batch dimension
            # Shape: (batch, channels, samples)
            wav = torch.from_numpy(audio).float().unsqueeze(0).to(self.device)
            
            # Apply model
            print("Applying Demucs model (this may take several minutes)...")
            with torch.no_grad():
                sources = apply_model(
                    self.model,
                    wav,
                    device=self.device,
                    progress=True,
                    num_workers=0
                )
            
            # sources shape: (batch, num_sources, channels, samples)
            # For htdemucs: sources are [drums, bass, other, vocals]
            source_names = self.model.sources
            print(f"Source names: {source_names}")
            
            # Find vocals index
            vocals_idx = source_names.index('vocals') if 'vocals' in source_names else -1
            
            if vocals_idx == -1:
                print("Vocals source not found in model output")
                return None, None
            
            # Extract vocals (channels, samples)
            vocals = sources[0, vocals_idx].cpu().numpy()
            
            # Create instrumental (sum all non-vocal sources)
            non_vocal_indices = [i for i, name in enumerate(source_names) if name != 'vocals']
            instrumental = sources[0, non_vocal_indices].sum(dim=0).cpu().numpy()
            
            # Create output directories
            vocals_dir = os.path.join(settings.storage_dir, "vocals")
            instrumental_dir = os.path.join(settings.storage_dir, "instrumentals")
            os.makedirs(vocals_dir, exist_ok=True)
            os.makedirs(instrumental_dir, exist_ok=True)
            
            # Output paths
            vocals_path = os.path.join(vocals_dir, f"{youtube_id}_vocals.wav")
            instrumental_path = os.path.join(instrumental_dir, f"{youtube_id}_instrumental.wav")
            
            # Transpose for soundfile (expects samples, channels)
            vocals_out = vocals.T
            instrumental_out = instrumental.T
            
            # Normalize to prevent clipping
            max_vocals = np.abs(vocals_out).max()
            max_instrumental = np.abs(instrumental_out).max()
            
            if max_vocals > 0:
                vocals_out = vocals_out * 0.95 / max_vocals
            if max_instrumental > 0:
                instrumental_out = instrumental_out * 0.95 / max_instrumental
            
            # Save using soundfile
            print(f"Saving vocals to: {vocals_path}")
            sf.write(vocals_path, vocals_out, model_sr)
            
            print(f"Saving instrumental to: {instrumental_path}")
            sf.write(instrumental_path, instrumental_out, model_sr)
            
            print(f"Separation complete!")
            return vocals_path, instrumental_path
            
        except Exception as e:
            print(f"Demucs separation error: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def cleanup(self, youtube_id: str):
        """Clean up temporary files for a song."""
        pass  # No temp files in this implementation


# Singleton instance
demucs_service = DemucsService()
