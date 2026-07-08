"""
S3 Image Upload Script
Downloads artist images from the URLs in 2026a2_songs.json and uploads them
to a PRIVATE S3 bucket. The backend generates presigned URLs for secure access.

Run this in AWS CloudShell or on an EC2 instance.
"""

import boto3
import json
import os
import urllib.request
import ssl

# ──────────────────────────────────────────────
# CONFIGURATION — Update the bucket name below
# ──────────────────────────────────────────────
REGION = "us-east-1"
BUCKET_NAME = "assignment2-music-artist-images-2026"

s3 = boto3.client("s3", region_name=REGION)


def create_bucket():
    print(f"Creating S3 bucket: {BUCKET_NAME}")
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        print(f"  Bucket '{BUCKET_NAME}' created.")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"  Bucket '{BUCKET_NAME}' already exists (owned by you).")
    except Exception as e:
        if "BucketAlreadyExists" in str(e):
            print(f"  Bucket name '{BUCKET_NAME}' is taken globally. Choose another name.")
            raise
        raise

    s3.put_public_access_block(
        Bucket=BUCKET_NAME,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  Public access blocked (images served via presigned URLs).")


def download_and_upload_images():
    json_path = os.path.join(os.path.dirname(__file__), "..", "2026a2_songs.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    uploaded = set()
    ctx = ssl.create_default_context()

    for song in data["songs"]:
        img_url = song["img_url"]
        filename = img_url.split("/")[-1]

        if filename in uploaded:
            continue

        print(f"  Downloading {filename}...")
        try:
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx) as response:
                image_data = response.read()

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=filename,
                Body=image_data,
                ContentType="image/jpeg",
            )
            print(f"    Uploaded to s3://{BUCKET_NAME}/{filename}")
            uploaded.add(filename)
        except Exception as e:
            print(f"    FAILED: {e}")

    return len(uploaded)


if __name__ == "__main__":
    print("=" * 60)
    print("  S3 Image Upload — AWS Academy Cloud Computing Assignment")
    print("=" * 60)

    create_bucket()
    total = download_and_upload_images()
    print(f"\n✓ Uploaded {total} unique artist images to s3://{BUCKET_NAME}/")
