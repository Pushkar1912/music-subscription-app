"""
AWS Lambda Function — Music Subscription API (Serverless Backend)
Deployed behind API Gateway REST API.

Implements a genuinely RESTful API:
  POST   /login          → Authenticate user
  POST   /register       → Register new user
  GET    /music          → Query music catalogue
  GET    /subscriptions  → Get user subscriptions
  POST   /subscriptions  → Subscribe to a song
  DELETE /subscriptions  → Unsubscribe from a song
"""

import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "assignment2-music-artist-images-2026")

# Lambda execution role must be set to LabRole in the Lambda console.
# boto3 automatically uses the Lambda execution role credentials.
dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3_client = boto3.client("s3", region_name=REGION)

login_table = dynamodb.Table("login")
music_table = dynamodb.Table("music")
subs_table = dynamodb.Table("subscriptions")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def generate_presigned_url(image_key):
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
    for item in items:
        item["image_url"] = generate_presigned_url(item.get("image_url", ""))
    return items


# ──────────────────────────────────────────────
# ROUTE HANDLERS
# ──────────────────────────────────────────────
def handle_login(body):
    email = body.get("email", "").strip()
    password = body.get("password", "").strip()

    if not email or not password:
        return response(400, {"error": "Email and password are required"})

    resp = login_table.get_item(Key={"email": email})
    user = resp.get("Item")

    if not user or user.get("password") != password:
        return response(401, {"error": "email or password is invalid"})

    return response(200, {
        "message": "Login successful",
        "email": email,
        "user_name": user.get("user_name", ""),
    })


def handle_register(body):
    email = body.get("email", "").strip()
    user_name = body.get("user_name", "").strip()
    password = body.get("password", "").strip()

    if not email or not user_name or not password:
        return response(400, {"error": "All fields are required"})

    existing = login_table.get_item(Key={"email": email})
    if "Item" in existing:
        return response(409, {"error": "The email already exists"})

    login_table.put_item(Item={
        "email": email,
        "user_name": user_name,
        "password": password,
    })

    return response(201, {"message": "Registration successful"})


def handle_query_music(params):
    title = (params.get("title") or "").strip()
    artist = (params.get("artist") or "").strip()
    year = (params.get("year") or "").strip()
    album = (params.get("album") or "").strip()

    if not title and not artist and not year and not album:
        return response(400, {"error": "At least one search field must be provided"})

    results = []

    if artist:
        if album and not title and not year:
            resp = music_table.query(
                IndexName="artist_album_index",
                KeyConditionExpression=Key("artist").eq(artist) & Key("album").eq(album),
            )
            results = resp.get("Items", [])
        elif year and not album and not title:
            resp = music_table.query(
                KeyConditionExpression=Key("artist").eq(artist)
                & Key("year_title").begins_with(f"{year}#"),
            )
            results = resp.get("Items", [])
        else:
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
        # Scan — only year or album provided (no index covers this pattern)
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

    results = enrich_with_image_url(results)

    if not results:
        return response(200, {"message": "No result is retrieved. Please query again", "results": []})

    return response(200, {"results": results})


def handle_get_subscriptions(params):
    email = (params.get("email") or "").strip()
    if not email:
        return response(400, {"error": "Email is required"})

    resp = subs_table.query(KeyConditionExpression=Key("email").eq(email))
    items = resp.get("Items", [])
    items = enrich_with_image_url(items)

    return response(200, {"subscriptions": items})


def handle_subscribe(body):
    email = body.get("email", "").strip()
    title = body.get("title", "")
    artist = body.get("artist", "")
    year = body.get("year", "")
    album = body.get("album", "")
    image_url = body.get("image_url", "")

    if not email or not title or not artist:
        return response(400, {"error": "Missing required fields"})

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

    return response(201, {"message": "Subscribed successfully"})


def handle_unsubscribe(body):
    email = body.get("email", "").strip()
    artist = body.get("artist", "")
    title = body.get("title", "")
    year = body.get("year", "")

    if not email or not artist or not title:
        return response(400, {"error": "Missing required fields"})

    song_id = f"{artist}#{title}#{year}"
    subs_table.delete_item(Key={"email": email, "song_id": song_id})

    return response(200, {"message": "Unsubscribed successfully"})


# ──────────────────────────────────────────────
# LAMBDA HANDLER (API Gateway Proxy Integration)
# ──────────────────────────────────────────────
def lambda_handler(event, context):
    http_method = event.get("httpMethod", "")
    path = event.get("resource", "") or event.get("path", "")
    params = event.get("queryStringParameters") or {}

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            body = {}

    if http_method == "OPTIONS":
        return response(200, {"message": "OK"})

    if path == "/login" and http_method == "POST":
        return handle_login(body)

    if path == "/register" and http_method == "POST":
        return handle_register(body)

    if path == "/music" and http_method == "GET":
        return handle_query_music(params)

    if path == "/subscriptions":
        if http_method == "GET":
            return handle_get_subscriptions(params)
        if http_method == "POST":
            return handle_subscribe(body)
        if http_method == "DELETE":
            return handle_unsubscribe(body)

    return response(404, {"error": f"Route not found: {http_method} {path}"})
