import boto3
import os
import uuid
import logging
from botocore.exceptions import NoCredentialsError
from app.core.config import settings

logger = logging.getLogger(__name__)

class S3Storage:
    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            region_name=getattr(settings, "AWS_REGION", "ap-southeast-1")
        )
        self.bucket_name = getattr(settings, "S3_BUCKET_NAME", None)

    def upload_file(self, file_path: str, folder: str = "streetview") -> str:
        """
        Uploads a local file to S3 and returns the public URL.
        """
        if not self.bucket_name:
            logger.warning("S3 bucket name not configured. Skipping S3 upload.")
            return None

        file_extension = os.path.splitext(file_path)[1]
        s3_file_name = f"{folder}/{uuid.uuid4()}{file_extension}"

        try:
            self.s3.upload_file(
                file_path, 
                self.bucket_name, 
                s3_file_name,
                ExtraArgs={'ACL': 'public-read'} # หากต้องการให้เป็น Public URL
            )
            
            location = self.s3.get_bucket_location(Bucket=self.bucket_name)['LocationConstraint']
            url = f"https://{self.bucket_name}.s3.{location}.amazonaws.com/{s3_file_name}"
            return url
        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return None

storage_service = S3Storage()
