"""Thin boto3 wrapper around the Garage bucket."""
from functools import lru_cache

import boto3
from botocore.config import Config
from django.conf import settings


def _client(endpoint):
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        config=Config(s3={'addressing_style': 'path'}, signature_version='s3v4'),
    )


@lru_cache(maxsize=1)
def get_client():
    return _client(settings.S3_ENDPOINT_URL)


@lru_cache(maxsize=1)
def _public_client():
    return _client(settings.S3_PUBLIC_ENDPOINT_URL)


def put_bytes(key, data, content_type='application/octet-stream'):
    get_client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=content_type)


def get_bytes(key):
    return get_client().get_object(Bucket=settings.S3_BUCKET, Key=key)['Body'].read()


def copy(src_key, dst_key):
    get_client().copy_object(
        Bucket=settings.S3_BUCKET, Key=dst_key, CopySource={'Bucket': settings.S3_BUCKET, 'Key': src_key}
    )


def delete_keys(keys):
    keys = list(keys)
    for i in range(0, len(keys), 1000):
        batch = [{'Key': k} for k in keys[i:i + 1000]]
        get_client().delete_objects(Bucket=settings.S3_BUCKET, Delete={'Objects': batch, 'Quiet': True})


def delete_prefix(prefix):
    paginator = get_client().get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=prefix):
        delete_keys(obj['Key'] for obj in page.get('Contents', []))


def presigned_url(key, expires=3600, filename=None):
    params = {'Bucket': settings.S3_BUCKET, 'Key': key}
    if filename:
        params['ResponseContentDisposition'] = f'inline; filename="{filename}"'
    return _public_client().generate_presigned_url('get_object', Params=params, ExpiresIn=expires)
