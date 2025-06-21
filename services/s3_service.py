# services/s3_service.py
import boto3
import os
import logging

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=os.getenv('R2_ENDPOINT_URL'),
                aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
                region_name='auto',
            )
            self.bucket_name = os.getenv('R2_BUCKET_NAME')
            if not all([self.s3_client, self.bucket_name, os.getenv('R2_ENDPOINT_URL')]):
                raise ValueError("Не все переменные для R2 установлены.")
            logger.info("S3Service (для Cloudflare R2): Клиент успешно инициализирован.")
        except Exception as e:
            logger.error(f"Ошибка инициализации S3Service: {e}")
            self.s3_client = None

    def upload_file(self, file_path, object_key):
        if not self.s3_client: return False
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_key)
            logger.info(f"Файл {file_path} успешно загружен в R2 как {object_key}")
            return True
        except Exception as e:
            logger.error(f"Ошибка загрузки файла в R2: {e}")
            return False

    def download_file(self, object_key: str, download_path: str) -> bool:
        if not self.s3_client: return False
        try:
            self.s3_client.download_file(self.bucket_name, object_key, download_path)
            logger.info(f"Файл {object_key} успешно скачан из R2 в {download_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка скачивания файла из R2: {e}")
            return False

    def delete_file(self, object_key: str) -> bool:
        if not self.s3_client: return False
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            logger.info(f"Файл {object_key} успешно удален из R2.")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления файла из R2: {e}")
            return False