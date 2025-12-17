"""
Cloud Storage Service with Local Fallback
Supports AWS S3, Cloudflare R2, MinIO, or any S3-compatible storage.
Falls back to local storage if cloud is not configured.
"""

import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional
from app.config import get_settings

settings = get_settings()


class StorageService:
    def __init__(self):
        self.cloud_enabled = settings.cloud_storage_enabled
        self.local_storage_dir = settings.storage_dir
        self.s3_client = None
        self.bucket_name = settings.s3_bucket_name
        
        # Ensure local storage directory exists
        os.makedirs(self.local_storage_dir, exist_ok=True)
        
        # Initialize S3 client if cloud storage is enabled
        if self.cloud_enabled and settings.aws_access_key_id:
            try:
                s3_config = {
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                    "region_name": settings.aws_region,
                }
                
                # For S3-compatible services like Cloudflare R2
                if settings.s3_endpoint_url:
                    s3_config["endpoint_url"] = settings.s3_endpoint_url
                
                self.s3_client = boto3.client("s3", **s3_config)
                print(f"Cloud storage initialized: {self.bucket_name}")
            except Exception as e:
                print(f"Failed to initialize cloud storage: {e}")
                self.cloud_enabled = False
    
    def get_local_path(self, filename: str, subfolder: str = "") -> str:
        """Get local file path."""
        if subfolder:
            folder = os.path.join(self.local_storage_dir, subfolder)
            os.makedirs(folder, exist_ok=True)
            return os.path.join(folder, filename)
        return os.path.join(self.local_storage_dir, filename)
    
    def get_cloud_key(self, filename: str, subfolder: str = "") -> str:
        """Get S3 object key."""
        if subfolder:
            return f"{subfolder}/{filename}"
        return filename
    
    def upload_file(self, local_path: str, filename: str, subfolder: str = "") -> str:
        """
        Upload file to cloud storage or keep in local storage.
        Returns the URL/path to access the file.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"File not found: {local_path}")
        
        if self.cloud_enabled and self.s3_client:
            try:
                key = self.get_cloud_key(filename, subfolder)
                
                # Determine content type
                content_type = "audio/wav"
                if filename.endswith(".mp3"):
                    content_type = "audio/mpeg"
                elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
                    content_type = "image/jpeg"
                elif filename.endswith(".png"):
                    content_type = "image/png"
                
                self.s3_client.upload_file(
                    local_path,
                    self.bucket_name,
                    key,
                    ExtraArgs={"ContentType": content_type}
                )
                
                # Generate public URL
                if settings.s3_endpoint_url:
                    # For R2 or custom endpoints
                    url = f"{settings.s3_endpoint_url}/{self.bucket_name}/{key}"
                else:
                    # Standard S3 URL
                    url = f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"
                
                print(f"Uploaded to cloud: {url}")
                return url
                
            except (ClientError, NoCredentialsError) as e:
                print(f"Cloud upload failed, using local storage: {e}")
        
        # Fallback to local storage - copy file to storage location
        import shutil
        dest_path = self.get_local_path(filename, subfolder)
        
        # Only copy if source and destination are different
        if os.path.abspath(local_path) != os.path.abspath(dest_path):
            shutil.copy2(local_path, dest_path)
            print(f"Copied to local storage: {dest_path}")
        
        return f"/storage/{subfolder}/{filename}" if subfolder else f"/storage/{filename}"
    
    def download_file(self, url_or_path: str, local_path: str) -> bool:
        """
        Download file from cloud storage to local path.
        """
        if url_or_path.startswith("http"):
            # Cloud URL - download from S3
            if self.cloud_enabled and self.s3_client:
                try:
                    # Extract key from URL
                    key = url_or_path.split(f"{self.bucket_name}/")[-1]
                    self.s3_client.download_file(self.bucket_name, key, local_path)
                    return True
                except ClientError as e:
                    print(f"Cloud download failed: {e}")
                    return False
        else:
            # Local path
            import shutil
            src = url_or_path.replace("/storage/", f"{self.local_storage_dir}/")
            if os.path.exists(src):
                shutil.copy2(src, local_path)
                return True
        return False
    
    def delete_file(self, url_or_path: str) -> bool:
        """Delete file from storage."""
        if url_or_path.startswith("http"):
            if self.cloud_enabled and self.s3_client:
                try:
                    key = url_or_path.split(f"{self.bucket_name}/")[-1]
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
                    return True
                except ClientError:
                    return False
        else:
            local_path = url_or_path.replace("/storage/", f"{self.local_storage_dir}/")
            if os.path.exists(local_path):
                os.remove(local_path)
                return True
        return False
    
    def file_exists(self, url_or_path: str) -> bool:
        """Check if file exists in storage."""
        if url_or_path.startswith("http"):
            if self.cloud_enabled and self.s3_client:
                try:
                    key = url_or_path.split(f"{self.bucket_name}/")[-1]
                    self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                    return True
                except ClientError:
                    return False
        else:
            local_path = url_or_path.replace("/storage/", f"{self.local_storage_dir}/")
            return os.path.exists(local_path)
        return False


# Singleton instance
storage_service = StorageService()
