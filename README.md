# Music Subscription App

This is a music subscription web app I built for a Cloud Computing assignment at RMIT. The idea was to take the same backend logic and deploy it three different ways on AWS: EC2, ECS Fargate, and API Gateway + Lambda, all hitting the same DynamoDB tables and S3 bucket. The frontend has a dropdown so you can literally switch which backend it's talking to while the app is running.

This repo only has my part of the group assignment in it, and I've cleaned out any real student data before pushing it here.

## Why build it three times?

The assignment wanted us to actually compare the common ways of running a REST API on AWS instead of just picking one and calling it done. So:

- **EC2**: just Flask running behind Gunicorn on a plain VM. You manage everything yourself.
- **ECS Fargate**: same app, containerized with Docker, sitting behind an Application Load Balancer. No servers to patch.
- **API Gateway + Lambda**: fully serverless version, rewritten as a Lambda handler since Lambda doesn't work like a normal Flask app.

Since all three share the exact same DynamoDB tables and S3 bucket, the frontend doesn't care which one it's calling. That part was honestly the most satisfying bit to get working.

## Architecture

```
                    ┌──────────────────────┐
                    │   S3 Static Website   │  <- Frontend (HTML/CSS/JS)
                    │   (Public Bucket)     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
            ┌──────│   Backend Selector    │──────┐
            │      │   (EC2/ECS/Lambda)    │      │
            │      └───────────────────────┘      │
            │                  │                   │
    ┌───────▼──────┐  ┌───────▼──────┐  ┌────────▼─────────┐
    │    EC2       │  │    ECS       │  │  API Gateway      │
    │  (Flask on   │  │  (Fargate +  │  │  + Lambda         │
    │   port 80)   │  │   ALB)       │  │  (Serverless)     │
    └───────┬──────┘  └───────┬──────┘  └────────┬─────────┘
            │                 │                    │
            └────────────┬────┘────────────────────┘
                         │
              ┌──────────▼───────────┐
              │     DynamoDB         │
              │  login / music (GSI+LSI) / subscriptions │
              └──────────┬───────────┘
                         │
              ┌──────────▼───────────┐
              │  S3 (Private Bucket) │  <- Artist images, served via presigned URLs
              └──────────────────────┘
```

## Some decisions I had to think through

**Figuring out the DynamoDB keys.** The dataset has 109 songs, and it turns out neither the title alone nor title+artist is unique (a few songs share titles across different artists, and some songs appear twice under different album releases). The only combination that's actually unique is artist + year + title. So I built the schema around that:

- Base table uses `artist` as the partition key and `year_title` (formatted as `year#title`) as the sort key. This groups everything by artist and sorts it by year automatically.
- Added an LSI (`artist_album_index`) so you can query "all songs by X in album Y" without scanning.
- Added a GSI (`title_artist_index`) so you can look things up by song title alone, since that's a completely different access pattern (different partition key).
- The API picks Query vs Scan depending on what fields you searched with, and only falls back to a full Scan when nothing else covers that combination of filters.

**Images aren't public.** The artist images sit in a private S3 bucket, and the backend generates presigned URLs (1 hour expiry) instead of just making the bucket public. Small thing but felt like the more correct way to do it.

**Same logic, written twice.** `backend/app.py` and `lambda/lambda_function.py` do the exact same thing, but Lambda doesn't run like a normal Flask app, so the Lambda version is a plain handler function that manually parses the event and builds the response. Writing both was a good way to actually see the difference between "framework does the work for you" and "you're wiring up the request/response yourself."

## API endpoints

| Method | Path | What it does |
|---|---|---|
| POST | `/login` | Log a user in |
| POST | `/register` | Create a new account |
| GET | `/music` | Search the catalogue by title, artist, year, and/or album |
| GET | `/subscriptions` | Get a user's subscribed songs |
| POST | `/subscriptions` | Subscribe to a song |
| DELETE | `/subscriptions` | Unsubscribe from a song |

## Stack

AWS (EC2, ECS Fargate, Lambda, API Gateway, DynamoDB, S3), Docker, Python, Flask, Gunicorn, boto3, plain HTML/CSS/JS on the frontend (no framework).

## What's in this repo

```
backend/    Flask app + Dockerfile, used for both the EC2 and ECS deployments
frontend/   Static HTML/CSS/JS, with the backend dropdown switcher
lambda/     The standalone Lambda handler for the serverless version
setup/      Scripts to create the DynamoDB tables, load sample data, and upload images to S3
DEPLOYMENT_GUIDE.md   Step by step notes I used to deploy all three versions on AWS Academy
```

Check `DEPLOYMENT_GUIDE.md` if you want the full walkthrough of setting this up on AWS.

## About the sample data

`setup/create_and_load.py` only loads a few placeholder demo accounts now (I removed my teammates' info and masked the student ID digits in mine), so it's safe to run as is.
