# services/s3_service.py
import boto3
from botocore.client import Config
import logging

# Импортируем наш новый объект настроек и константы
from config import settings
from constants import S3_URL_EXPIRATION_SECONDS

class S3Service:
    def __init__(self):
        # Используем настройки из config.py
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3.r2_endpoint_url,
            aws_access_key_id=settings.s3.r2_access_key_id,
            aws_secret_access_key=settings.s3.r2_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        self.bucket_name = settings.s3.r2_bucket_name
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