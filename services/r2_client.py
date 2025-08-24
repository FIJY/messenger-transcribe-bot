import boto3
import os

def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    )

def upload_to_r2(local_path: str, object_name: str) -> str:
    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")
    client.upload_file(local_path, bucket, object_name)
    return f"{os.getenv('R2_ENDPOINT_URL')}/{bucket}/{object_name}"

def download_from_r2(object_name: str, local_path: str):
    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")
    client.download_file(bucket, object_name, local_path)
    return local_path
