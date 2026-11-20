import os

import boto3
from botocore.config import Config


def bucket():
    return (
        boto3.client(
            "s3",
            endpoint_url=os.environ["AWS_ENDPOINT_URL"],
            region_name=os.getenv("AWS_DEFAULT_REGION", "auto"),
            config=Config(signature_version="s3v4"),
        ),
        os.environ["AWS_S3_BUCKET_NAME"],
    )
