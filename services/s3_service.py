# services/s3_service.py
import boto3
from botocore.client import Config
import logging

# --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
# Заменяем неправильный импорт на правильный, из нашего пакета 'config'
from config import settings, S3_URL_EXPIRATION_SECONDS
# --- КОНЕЦ ИСПРАВЛЕНИЯ ---

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        self.bucket_name = settings.R2_BUCKET_NAME
        logging.info("S3 Service initialized.")

    def upload_file(self, file_path, object_name):
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            logging.info(f"File {file_path} uploaded to {self.bucket_name}/{object_name}")
            return f"{object_name}"
        except Exception as e:
            logging.error(f"Error uploading file to S3: {e}")
            return None

    def get_presigned_url(self, object_name):
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=S3_URL_EXPIRATION_SECONDS,
            )
            return url
        except Exception as e:
            logging.error(f"Error generating presigned URL for {object_name}: {e}")
            return None