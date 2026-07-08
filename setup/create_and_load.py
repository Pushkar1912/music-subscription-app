"""
DynamoDB Table Creation and Data Loading Script
Run this in AWS CloudShell or on an EC2 instance (NOT locally).

=== DATA CARDINALITY ANALYSIS ===
The 2026a2_songs.json dataset contains 109 songs. Key observations:

1. 'title' alone is NOT unique:
   - "Bad Blood" appears for both Taylor Swift and Kendrick Lamar
   - "Rivers of Babylon" appears for Sublime and The Melodians
   - "The Needle and the Damage Done" appears for Neil Young and The Pretenders

2. 'title + artist' is NOT unique:
   - "Delicate" by Taylor Swift appears in 2017 (Reputation) and 2018 (Reputation Deluxe)
   - "I Won't Give Up" by Jason Mraz appears in 2012 and 2021
   - "Rivers of Babylon" by The Melodians appears in 1970 and 2003
   - "We Are Never Ever Getting Back Together" by Taylor Swift in 2012 and 2013

3. 'artist + title + year' IS unique across all 109 songs.

=== KEY SCHEMA DESIGN ===
Music Table:
  - Partition Key: 'artist' (String)
  - Sort Key: 'year_title' (String) — formatted as "{year}#{title}"
  Rationale: Using 'artist' as PK groups all songs by artist, enabling efficient
  Query operations for "find all songs by X". The composite sort key 'year_title'
  ensures uniqueness (no overwrites) and enables range queries by year within an
  artist using begins_with(). The year-first ordering naturally sorts an artist's
  catalogue chronologically.

  LSI (artist_album_index): PK=artist, SK=album
  Rationale: Supports queries like "all songs by Taylor Swift in album Fearless"
  without scanning. Shares the same partition key as the base table (DynamoDB
  LSI requirement).

  GSI (title_artist_index): PK=title, SK=artist
  Rationale: Supports queries by title (e.g., "find all versions of Rivers of
  Babylon") using a Query instead of a Scan. Different PK allows a completely
  different access pattern.

Query vs Scan Strategy:
  - Query (base table): when artist is known
  - Query (LSI): when artist + album are known
  - Query (GSI): when title is known (with optional artist filter)
  - Scan: when only year or album is provided without artist/title — no index
    covers this access pattern, so a filtered Scan is the appropriate fallback.
"""

import boto3
import json
import time
import sys
import os

REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ddb_client = boto3.client("dynamodb", region_name=REGION)


def wait_for_table(table_name):
    """Wait until a DynamoDB table becomes ACTIVE."""
    waiter = ddb_client.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    print(f"  Table '{table_name}' is now ACTIVE.")


# ──────────────────────────────────────────────
# LOGIN TABLE
# ──────────────────────────────────────────────
def create_login_table():
    print("Creating 'login' table...")
    try:
        table = dynamodb.create_table(
            TableName="login",
            KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        wait_for_table("login")
    except ddb_client.exceptions.ResourceInUseException:
        print("  'login' table already exists.")


def load_login_data():
    """
    Load sample login entries into the login table.
    Pattern: email = s4xxxxxxx@student.rmit.edu.au (student ID anonymized),
    user_name = placeholder username, password rotates for demo purposes.
    """
    print("Loading login data...")
    table = dynamodb.Table("login")

    login_data = [
        {"email": "s4xxxxxx0@student.rmit.edu.au", "user_name": "Username1", "password": "012345"},
        {"email": "s4xxxxxx4@student.rmit.edu.au", "user_name": "Username2", "password": "456789"},
        {"email": "s4xxxxxx8@student.rmit.edu.au", "user_name": "Username3", "password": "890123"},
    ]

    with table.batch_writer() as batch:
        for item in login_data:
            batch.put_item(Item=item)

    print(f"  Loaded {len(login_data)} login entries.")


# ──────────────────────────────────────────────
# MUSIC TABLE  (with LSI + GSI)
# ──────────────────────────────────────────────
def create_music_table():
    print("Creating 'music' table with LSI and GSI...")
    try:
        table = dynamodb.create_table(
            TableName="music",
            KeySchema=[
                {"AttributeName": "artist", "KeyType": "HASH"},
                {"AttributeName": "year_title", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "artist", "AttributeType": "S"},
                {"AttributeName": "year_title", "AttributeType": "S"},
                {"AttributeName": "album", "AttributeType": "S"},
                {"AttributeName": "title", "AttributeType": "S"},
            ],
            LocalSecondaryIndexes=[
                {
                    "IndexName": "artist_album_index",
                    "KeySchema": [
                        {"AttributeName": "artist", "KeyType": "HASH"},
                        {"AttributeName": "album", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "title_artist_index",
                    "KeySchema": [
                        {"AttributeName": "title", "KeyType": "HASH"},
                        {"AttributeName": "artist", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        wait_for_table("music")
        time.sleep(5)
    except ddb_client.exceptions.ResourceInUseException:
        print("  'music' table already exists.")


def load_music_data():
    print("Loading music data from 2026a2_songs.json...")
    table = dynamodb.Table("music")

    json_path = os.path.join(os.path.dirname(__file__), "..", "2026a2_songs.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    with table.batch_writer() as batch:
        for song in data["songs"]:
            item = {
                "artist": song["artist"],
                "year_title": f"{song['year']}#{song['title']}",
                "title": song["title"],
                "year": song["year"],
                "album": song["album"],
                "image_url": song["img_url"].split("/")[-1],
            }
            batch.put_item(Item=item)
            count += 1

    print(f"  Loaded {count} songs (all unique by artist + year + title — zero overwrites).")


# ──────────────────────────────────────────────
# SUBSCRIPTIONS TABLE
# ──────────────────────────────────────────────
def create_subscriptions_table():
    print("Creating 'subscriptions' table...")
    try:
        table = dynamodb.create_table(
            TableName="subscriptions",
            KeySchema=[
                {"AttributeName": "email", "KeyType": "HASH"},
                {"AttributeName": "song_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "song_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        wait_for_table("subscriptions")
    except ddb_client.exceptions.ResourceInUseException:
        print("  'subscriptions' table already exists.")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  DynamoDB Setup — AWS Academy Cloud Computing Assignment")
    print("=" * 60)

    create_login_table()
    create_music_table()
    create_subscriptions_table()

    load_login_data()
    load_music_data()

    print("\n✓ All tables created and data loaded successfully.")
    print("  Tables: login, music (with GSI + LSI), subscriptions")
