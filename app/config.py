import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:12345678@localhost:5432/postgres"
    
    # Cloud Storage
    cloud_storage_enabled: bool = False
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "melodyyy-music"
    s3_endpoint_url: str = ""
    
    # Whisper
    whisper_model: str = "base"
    
    # Demucs
    demucs_model: str = "htdemucs"
    
    # Local storage paths
    storage_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
