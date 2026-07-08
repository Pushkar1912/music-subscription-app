"""
Flask Backend — Music Subscription Web Application
Used for BOTH EC2 and ECS deployments (same code, different hosting).

Runs on port 80 as required by the assignment.
"""

import os
import boto3
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from boto3.dynamodb.conditions import Key, Attr

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cloud-computing-2026-secret")

CORS(app, supports_credentials=True, origins="*")

# ──────────────────────────────────────────────
# AWS Configuration
# ──────────────────────────────────────────────
REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "assignment2-music-artist-images-2026")

# boto3 uses the default credential chain:
#   CloudShell  → automatic session credentials
#   EC2         → LabInstanceProfile (attach in launch config)
#   ECS Fargate → LabRole (set as task role in task definition)
# No IAM role creation needed — AWS Academy provides LabRole.
dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3_client = boto3.client("s3", region_name=REGION)

login_table = dynamodb.Table("login")
music_table = dynamodb.Table("music")
subs_table = dynamodb.Table("subscriptions")


def generate_presigned_url(image_key):
    """Generate a presigned URL for secure S3 image access (1 hour expiry)."""
    if not image_key:
        return ""
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": image_key},
            ExpiresIn=3600,
        )
    except Exception:
        return ""


def enrich_with_image_url(items):
    """Replace image_url keys with presigned S3 URLs."""
    for item in items:
        item["image_url"] = generate_presigned_url(item.get("image_url", ""))
    return items


# ──────────────────────────────────────────────
# AUTH ENDPOINTS
# ──────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        resp = login_table.get_item(Key={"email": email})
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}. Check IAM role (LabInstanceProfile for EC2, LabRole for ECS)."}), 500

    user = resp.get("Item")

    if not user or user.get("password") != password:
        return jsonify({"error": "email or password is invalid"}), 401

    session["email"] = email
    return jsonify({
        "message": "Login successful",
        "email": email,
        "user_name": user.get("user_name", ""),
    })


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email", "").strip()
    user_name = data.get("user_name", "").strip()
    password = data.get("password", "").strip()

    if not email or not user_name or not password:
        return jsonify({"error": "All fields are required"}), 400

    existing = login_table.get_item(Key={"email": email})
    if "Item" in existing:
        return jsonify({"error": "The email already exists"}), 409

    login_table.put_item(Item={
        "email": email,
        "user_name": user_name,
        "password": password,
    })

    return jsonify({"message": "Registration successful"}), 201


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


# ──────────────────────────────────────────────
# MUSIC QUERY ENDPOINT
# ──────────────────────────────────────────────
@app.route("/api/music", methods=["GET"])
def query_music():
    """
    Query music using the most efficient access pattern available.

    Strategy (Query vs Scan):
      - artist provided → Query base table (PK = artist)
      - artist + album  → Query LSI 'artist_album_index'
      - artist + year   → Query base table with begins_with(SK, year)
      - title provided (no artist) → Query GSI 'title_artist_index'
      - only year or only album    → Scan with filter (no index covers this)
    """
    title = request.args.get("title", "").strip()
    artist = request.args.get("artist", "").strip()
    year = request.args.get("year", "").strip()
    album = request.args.get("album", "").strip()

    if not title and not artist and not year and not album:
        return jsonify({"error": "At least one search field must be provided"}), 400

    results = []

    try:
        if artist:
            if album and not title and not year:
                # Query LSI: artist + album
                resp = music_table.query(
                    IndexName="artist_album_index",
                    KeyConditionExpression=Key("artist").eq(artist) & Key("album").eq(album),
                )
                results = resp.get("Items", [])
            elif year and not album and not title:
                # Query base table: artist + year (using begins_with on sort key)
                resp = music_table.query(
                    KeyConditionExpression=Key("artist").eq(artist)
                    & Key("year_title").begins_with(f"{year}#"),
                )
                results = resp.get("Items", [])
            else:
                # Query base table on artist, filter the rest
                key_expr = Key("artist").eq(artist)
                if year:
                    key_expr = key_expr & Key("year_title").begins_with(f"{year}#")

                resp = music_table.query(KeyConditionExpression=key_expr)
                results = resp.get("Items", [])

                if title:
                    results = [r for r in results if r.get("title", "").lower() == title.lower()]
                if album:
                    results = [r for r in results if r.get("album", "").lower() == album.lower()]

        elif title:
            # Query GSI: title (optionally with artist sort key)
            resp = music_table.query(
                IndexName="title_artist_index",
                KeyConditionExpression=Key("title").eq(title),
            )
            results = resp.get("Items", [])

            if year:
                results = [r for r in results if r.get("year") == year]
            if album:
                results = [r for r in results if r.get("album", "").lower() == album.lower()]

        else:
            # Scan with filter — no artist or title provided
            filter_expr = None
            if year:
                filter_expr = Attr("year").eq(year)
            if album:
                album_filter = Attr("album").eq(album)
                filter_expr = filter_expr & album_filter if filter_expr else album_filter

            scan_kwargs = {}
            if filter_expr:
                scan_kwargs["FilterExpression"] = filter_expr

            resp = music_table.scan(**scan_kwargs)
            results = resp.get("Items", [])

            while "LastEvaluatedKey" in resp:
                scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
                resp = music_table.scan(**scan_kwargs)
                results.extend(resp.get("Items", []))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = enrich_with_image_url(results)

    if not results:
        return jsonify({"message": "No result is retrieved. Please query again", "results": []}), 200

    return jsonify({"results": results})


# ──────────────────────────────────────────────
# SUBSCRIPTION ENDPOINTS
# ──────────────────────────────────────────────
@app.route("/api/subscriptions", methods=["GET"])
def get_subscriptions():
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    resp = subs_table.query(KeyConditionExpression=Key("email").eq(email))
    items = resp.get("Items", [])
    items = enrich_with_image_url(items)

    return jsonify({"subscriptions": items})


@app.route("/api/subscriptions", methods=["POST"])
def subscribe():
    data = request.get_json()
    email = data.get("email", "").strip()
    title = data.get("title", "")
    artist = data.get("artist", "")
    year = data.get("year", "")
    album = data.get("album", "")
    image_url = data.get("image_url", "")

    if not email or not title or not artist:
        return jsonify({"error": "Missing required fields"}), 400

    song_id = f"{artist}#{title}#{year}"

    subs_table.put_item(Item={
        "email": email,
        "song_id": song_id,
        "title": title,
        "artist": artist,
        "year": year,
        "album": album,
        "image_url": image_url,
    })

    return jsonify({"message": "Subscribed successfully"}), 201


@app.route("/api/subscriptions", methods=["DELETE"])
def unsubscribe():
    data = request.get_json()
    email = data.get("email", "").strip()
    artist = data.get("artist", "")
    title = data.get("title", "")
    year = data.get("year", "")

    if not email or not artist or not title:
        return jsonify({"error": "Missing required fields"}), 400

    song_id = f"{artist}#{title}#{year}"

    subs_table.delete_item(Key={"email": email, "song_id": song_id})

    return jsonify({"message": "Unsubscribed successfully"})


# ──────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
