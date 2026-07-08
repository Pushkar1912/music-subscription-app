# AWS Academy Deployment Guide — Music Subscription Application

> **CRITICAL**: Everything MUST be deployed on AWS. Do NOT run anything locally.
> Use **AWS CloudShell** (free, built into the console) to run all setup scripts.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Start Your AWS Academy Lab](#2-start-your-aws-academy-lab)
3. [Step A: Create DynamoDB Tables & Load Data](#step-a-create-dynamodb-tables--load-data)
4. [Step B: Create S3 Bucket & Upload Artist Images](#step-b-create-s3-bucket--upload-artist-images)
5. [Step C: Host Frontend on S3 (Static Website)](#step-c-host-frontend-on-s3-static-website)
6. [Step D: Deploy Backend on EC2](#step-d-deploy-backend-on-ec2)
7. [Step E: Deploy Backend on ECS (Fargate)](#step-e-deploy-backend-on-ecs-fargate)
8. [Step F: Deploy Backend on API Gateway + Lambda](#step-f-deploy-backend-on-api-gateway--lambda)
9. [Step G: Update Frontend with Backend URLs](#step-g-update-frontend-with-backend-urls)
10. [Testing Checklist](#testing-checklist)

---

## 1. Prerequisites

- AWS Academy Learner Lab account
- All project files from the `Cloud Computing/` folder
- The lab uses the **LabRole** IAM role (pre-created — do NOT create new IAM roles)

---

## 2. Start Your AWS Academy Lab

1. Go to your **AWS Academy** course → **Modules** → **Learner Lab**
2. Click **Start Lab** (wait for the status indicator to turn green)
3. Click **AWS** (the green indicator) to open the AWS Management Console
4. Verify you are in the **us-east-1 (N. Virginia)** region (top-right dropdown)

---

## Step A: Create DynamoDB Tables & Load Data

### Using AWS CloudShell

1. In the AWS Console, click the **CloudShell** icon (terminal icon, top-right bar)
2. Wait for CloudShell to initialize

3. Upload the required files to CloudShell:
   - Click **Actions** (top-right of the CloudShell window) → **Upload file**
   - Upload `create_and_load.py` (from the `setup/` folder)
   - Click **Actions** → **Upload file** again
   - Upload `2026a2_songs.json` (from the project root)

4. Organize files and run:
```bash
mkdir -p setup
mv create_and_load.py setup/
python3 setup/create_and_load.py
```

5. **Verify** in DynamoDB Console:
   - Go to **DynamoDB** → **Tables**
   - You should see 3 tables: `login`, `music`, `subscriptions`
   - Click on `music` → **Indexes** tab → verify `artist_album_index` (LSI) and `title_artist_index` (GSI) exist
   - Click **Explore table items** → verify data is loaded (109 songs in music, 10 users in login)

---

## Step B: Create S3 Bucket & Upload Artist Images

1. **Choose a globally unique bucket name** for images. For example:
   `assignment2-music-artist-images-2026`

2. In CloudShell, upload the image script:
   - Click **Actions** → **Upload file** → upload `upload_images.py` (from the `setup/` folder)

3. Move it and update the bucket name:
```bash
mv upload_images.py setup/
sed -i 's/your-music-artist-images-bucket/assignment2-music-artist-images-2026/g' setup/upload_images.py
```

4. Run the upload script:
```bash
python3 setup/upload_images.py
```

5. **Verify** in S3 Console:
   - Go to **S3** → find your images bucket
   - Verify artist images (`.jpg` files) are uploaded
   - Verify **Block all public access** is ON (images are private, served via presigned URLs)

6. Clean up CloudShell:
```bash
rm -rf setup/ 2026a2_songs.json
```

---

## Step C: Host Frontend on S3 (Static Website)

### C1. Create a Frontend S3 Bucket

1. Go to **S3** → **Create bucket**
2. Bucket name: `assignment2-music-frontend-2026` (globally unique)
3. Region: `us-east-1`
4. **Uncheck** "Block all public access" (the frontend HTML/CSS/JS must be publicly readable)
   - Check the acknowledgment box
5. Click **Create bucket**

### C2. Enable Static Website Hosting

1. Click on the new bucket → **Properties** tab
2. Scroll to **Static website hosting** → **Edit**
3. Select **Enable**
4. Index document: `index.html`
5. Click **Save changes**
6. Note the **Bucket website endpoint** URL (e.g., `http://assignment2-music-frontend-2026.s3-website-us-east-1.amazonaws.com`) — this is your frontend URL

### C3. Set Bucket Policy for Public Read

1. Go to **Permissions** tab → **Bucket policy** → **Edit**
2. Paste this policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::assignment2-music-frontend-2026/*"
        }
    ]
}
```
3. Click **Save changes**

### C4. Upload Frontend Files

1. In CloudShell, upload all 5 frontend files one by one:
   - Click **Actions** → **Upload file** → upload `index.html`
   - Repeat for `register.html`, `main.html`, `style.css`, `app.js`
   (All files are from the `frontend/` folder)

2. Upload them to your frontend S3 bucket using the AWS CLI:
```bash
aws s3 cp index.html s3://assignment2-music-frontend-2026/
aws s3 cp register.html s3://assignment2-music-frontend-2026/
aws s3 cp main.html s3://assignment2-music-frontend-2026/
aws s3 cp style.css s3://assignment2-music-frontend-2026/ --content-type "text/css"
aws s3 cp app.js s3://assignment2-music-frontend-2026/ --content-type "application/javascript"
```

3. Clean up CloudShell:
```bash
rm -f index.html register.html main.html style.css app.js
```

> **Note**: You will need to re-upload `app.js` after updating the backend URLs in Step G.

### C5. Test Frontend

- Open the **Bucket website endpoint** URL in your browser
- You should see the login page

---

## Step D: Deploy Backend on EC2

### D1. Launch an EC2 Instance

1. Go to **EC2** → **Launch instance**
2. Configure:
   - **Name**: `music-backend-ec2`
   - **AMI**: Amazon Linux 2023 AMI (free tier eligible)
   - **Instance type**: `t3.micro`
   - **Key pair**: Create or select an existing key pair (for SSH access)
   - **Network settings**: Click **Edit**
     - Auto-assign public IP: **Enable**
     - Security group: **Create security group**
       - Name: `music-backend-sg`
       - Add rule: **HTTP** (port 80) from **Anywhere (0.0.0.0/0)**
       - Add rule: **SSH** (port 22) from **My IP** (for remote access)
   - **Advanced details**:
     - IAM instance profile: **LabInstanceProfile**
3. Click **Launch instance**
4. Wait until instance state is **Running** and status check shows **2/2 checks passed**
5. Note the **Public IPv4 address**

### D2. Connect and Deploy

1. Click on the instance → **Connect** → **EC2 Instance Connect** → **Connect**
   (This opens a browser-based terminal — no local SSH needed)

2. Install dependencies:
```bash
sudo yum update -y
sudo yum install -y python3-pip
```

3. Create the app directory:
```bash
mkdir -p /home/ec2-user/music-app
cd /home/ec2-user/music-app
```

4. Upload `app.py` to the EC2 instance. Since EC2 Instance Connect doesn't have an upload button, use one of these methods:

**Method A — Copy from S3 (recommended):**
   First, upload `app.py` (from the `backend/` folder) to your images S3 bucket temporarily via CloudShell:
```bash
# In CloudShell — upload app.py first via Actions → Upload file, then:
aws s3 cp app.py s3://assignment2-music-artist-images-2026/app.py
rm app.py
```
   Then in the EC2 terminal:
```bash
aws s3 cp s3://assignment2-music-artist-images-2026/app.py app.py
aws s3 rm s3://assignment2-music-artist-images-2026/app.py
```

**Method B — Paste into nano:**
```bash
nano app.py
```
   - Open `backend/app.py` from your local folder → Select all → Copy
   - Right-click in the EC2 terminal → Paste → Ctrl+O → Enter → Ctrl+X

5. **IMPORTANT** — Update the S3 bucket name in the app:
```bash
sed -i 's/your-music-artist-images-bucket/assignment2-music-artist-images-2026/g' app.py
```

6. Install Python packages and run on port 80:
```bash
pip3 install flask flask-cors boto3 gunicorn
sudo $(which gunicorn) --bind 0.0.0.0:80 --workers 2 --timeout 120 app:app --daemon
```

7. **Verify**: Open `http://<EC2-Public-IP>/api/health` in your browser. You should see:
```json
{"status": "healthy"}
```

### D3. Make It Persistent (Optional)

To keep the server running after disconnecting:

```bash
sudo tee /etc/systemd/system/music-app.service << 'EOF'
[Unit]
Description=Music App Backend
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/music-app
ExecStart=/usr/local/bin/gunicorn --bind 0.0.0.0:80 --workers 2 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable music-app
sudo systemctl start music-app
```

---

## Step E: Deploy Backend on ECS (Fargate)

### E1. Create an ECR Repository

1. Go to **Amazon ECR** → **Repositories** → **Create repository**
2. Repository name: `music-backend`
3. Click **Create repository**
4. Click on the repository → **View push commands** (keep this open)

### E2. Build and Push Docker Image (from CloudShell)

1. Open **CloudShell**
2. Upload the 3 backend files one by one:
   - Click **Actions** → **Upload file** → upload `app.py` (from `backend/`)
   - Click **Actions** → **Upload file** → upload `requirements.txt` (from `backend/`)
   - Click **Actions** → **Upload file** → upload `Dockerfile` (from `backend/`)

3. Organize files and update the S3 bucket name:
```bash
mkdir -p backend
mv app.py requirements.txt Dockerfile backend/
sed -i 's/your-music-artist-images-bucket/assignment2-music-artist-images-2026/g' backend/app.py
```

4. Build and push the Docker image:
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

cd backend
docker build -t music-backend .
docker tag music-backend:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/music-backend:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/music-backend:latest
cd ..
```

5. Clean up:
```bash
rm -rf backend/
```

### E3. Create ECS Cluster

1. Go to **Amazon ECS** → **Clusters** → **Create cluster**
2. Cluster name: `music-cluster`
3. Infrastructure: **AWS Fargate (serverless)** (should be selected by default)
4. Click **Create**

### E4. Create Task Definition

1. Go to **ECS** → **Task definitions** → **Create new task definition**
2. Task definition family: `music-backend-task`
3. Launch type: **AWS Fargate**
4. Operating system: **Linux/X86_64**
5. Task size:
   - CPU: `0.25 vCPU`
   - Memory: `0.5 GB`
6. Task role: **LabRole**
7. Task execution role: **LabRole**
8. Container:
   - Name: `music-backend`
   - Image URI: `<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/music-backend:latest`
   - Port mappings: Container port `80`, Protocol `TCP`
   - Environment variables (add these):
     - `S3_BUCKET` = `assignment2-music-artist-images-2026`
     - `AWS_REGION` = `us-east-1`
9. Click **Create**

### E5. Create an Application Load Balancer (ALB)

1. Go to **EC2** → **Load Balancers** → **Create Load Balancer**
2. Choose **Application Load Balancer**
3. Configure:
   - Name: `music-alb`
   - Scheme: **Internet-facing**
   - IP address type: **IPv4**
   - Listeners: **HTTP : 80**
   - Availability Zones: select **at least 2 subnets** (us-east-1a and us-east-1b)
4. Security group:
   - Create new: `music-alb-sg`
   - Inbound rule: **HTTP** (port 80) from **Anywhere (0.0.0.0/0)**
5. Target group:
   - Create target group: **IP addresses** type
   - Name: `music-ecs-tg`
   - Protocol: **HTTP**, Port: **80**
   - Health check path: `/api/health`
   - Click **Create target group** (don't register targets manually — ECS does this)
6. Select the target group in the ALB listener
7. Click **Create load balancer**
8. Note the **ALB DNS name** (e.g., `music-alb-123456.us-east-1.elb.amazonaws.com`)

### E6. Create ECS Service

1. Go to **ECS** → **Clusters** → `music-cluster` → **Services** tab → **Create**
2. Configure:
   - Launch type: **FARGATE**
   - Task definition: `music-backend-task` (latest revision)
   - Service name: `music-backend-service`
   - Number of tasks: `1`
3. Networking:
   - VPC: default VPC
   - Subnets: select same subnets as ALB
   - Security group: Create new or use existing
     - Inbound: **HTTP** (port 80) from **the ALB security group** (or 0.0.0.0/0)
   - Public IP: **TURNED ON**
4. Load balancing:
   - Load balancer type: **Application Load Balancer**
   - Select `music-alb`
   - Listener: `80:HTTP`
   - Target group: `music-ecs-tg`
5. Click **Create**

6. **Verify**: Wait 2-3 minutes, then open `http://<ALB-DNS-Name>/api/health`

---

## Step F: Deploy Backend on API Gateway + Lambda

### F1. Create Lambda Function

1. Go to **Lambda** → **Create function**
2. Configure:
   - Function name: `music-backend-lambda`
   - Runtime: **Python 3.12**
   - Architecture: **x86_64**
   - Permissions: **Use an existing role** → select **LabRole**
3. Click **Create function**

4. In the function code editor:
   - Delete the default code
   - Open `lambda/lambda_function.py` from your local folder → Select all → Copy
   - **Paste** the entire code into the Lambda console editor
   - Click **Deploy**

5. Configure environment variables:
   - Go to **Configuration** → **Environment variables** → **Edit**
   - Add:
     - `S3_BUCKET` = `assignment2-music-artist-images-2026`
     - `AWS_REGION` = `us-east-1`
   - Click **Save**

6. Increase timeout:
   - Go to **Configuration** → **General configuration** → **Edit**
   - Timeout: `30` seconds
   - Memory: `256` MB
   - Click **Save**

### F2. Create API Gateway REST API

1. Go to **API Gateway** → **Create API**
2. Choose **REST API** (NOT "REST API Private") → **Build**
3. Configure:
   - API name: `music-api`
   - Endpoint type: **Regional**
4. Click **Create API**

### F3. Create Resources and Methods

You need to create these resources and their HTTP methods:

#### Resource: /login
1. Click **Create Resource**
2. Resource name: `login`, Resource path: `/login`
3. **Enable CORS** (check the box)
4. Click **Create Resource**
5. Select `/login` → **Create Method**
6. Method type: **POST**
7. Integration type: **Lambda Function**
8. Lambda proxy integration: **ON** (check the box)
9. Lambda function: `music-backend-lambda`
10. Click **Create method**

#### Resource: /register
1. Click on `/` (root) → **Create Resource**
2. Resource name: `register`, path: `/register`
3. **Enable CORS**
4. Click **Create Resource**
5. Select `/register` → **Create Method** → **POST** → Lambda proxy → `music-backend-lambda`

#### Resource: /music
1. Click on `/` → **Create Resource**
2. Resource name: `music`, path: `/music`
3. **Enable CORS**
4. Click **Create Resource**
5. Select `/music` → **Create Method** → **GET** → Lambda proxy → `music-backend-lambda`

#### Resource: /subscriptions
1. Click on `/` → **Create Resource**
2. Resource name: `subscriptions`, path: `/subscriptions`
3. **Enable CORS**
4. Click **Create Resource**
5. Select `/subscriptions` → create **three methods**:
   - **GET** → Lambda proxy → `music-backend-lambda`
   - **POST** → Lambda proxy → `music-backend-lambda`
   - **DELETE** → Lambda proxy → `music-backend-lambda`

### F4. Enable CORS (Important!)

For **each resource** (`/login`, `/register`, `/music`, `/subscriptions`):
1. Select the resource
2. Click **Enable CORS**
3. Access-Control-Allow-Origin: `*`
4. Access-Control-Allow-Headers: `Content-Type,Authorization`
5. Access-Control-Allow-Methods: select all methods for that resource + OPTIONS
6. Click **Save**

### F5. Deploy the API

1. Click **Deploy API**
2. Stage: **New Stage**
3. Stage name: `prod`
4. Click **Deploy**
5. Note the **Invoke URL** (e.g., `https://abc123def.execute-api.us-east-1.amazonaws.com/prod`)

### F6. Verify

Open in browser: `https://<API-ID>.execute-api.us-east-1.amazonaws.com/prod/music?artist=Taylor Swift`

You should see JSON results with Taylor Swift's songs.

---

## Step G: Update Frontend with Backend URLs

1. In **CloudShell**, download `app.js` from S3:
```bash
aws s3 cp s3://assignment2-music-frontend-2026/app.js app.js
```

2. Edit it with `nano`:
```bash
nano app.js
```
   Find the `BACKENDS` object near the top and replace the placeholder URLs:
```javascript
const BACKENDS = {
    ec2:    "http://<YOUR-EC2-PUBLIC-IP>/api",
    ecs:    "http://<YOUR-ALB-DNS-NAME>/api",
    lambda: "https://<YOUR-API-GATEWAY-ID>.execute-api.us-east-1.amazonaws.com/prod",
};
```
   - Save (**Ctrl+O** → Enter) and exit (**Ctrl+X**)

3. Re-upload the updated file to S3:
```bash
aws s3 cp app.js s3://assignment2-music-frontend-2026/ --content-type "application/javascript"
rm app.js
```

4. **Test** the frontend by opening the S3 website endpoint URL.
   - Try logging in, registering, querying music, subscribing, and removing subscriptions
   - Switch backends using the dropdown to verify all three work

---

## Testing Checklist

Use this checklist during your demo:

### Login Page
- [ ] Enter invalid credentials → shows "email or password is invalid"
- [ ] Enter valid credentials → redirects to main page

### Register Page
- [ ] Register with existing email → shows "The email already exists"
- [ ] Register with new email → redirects to login page
- [ ] Login with the newly registered account

### Main Page
- [ ] User name displayed in the header
- [ ] Subscription area is initially empty for new users
- [ ] Query: search by artist (e.g., "Taylor Swift") → shows results with images
- [ ] Query: search by artist + album (e.g., "Taylor Swift" + "Fearless") → filtered results
- [ ] Query: search by year (e.g., "1974") → shows results (uses Scan)
- [ ] Query: search by title (e.g., "Bad Blood") → shows both versions
- [ ] Query with no results → shows "No result is retrieved. Please query again"
- [ ] Subscribe to a song → appears in subscription area
- [ ] Remove a subscription → removed from subscription area
- [ ] Logout → redirects to login page, session cleared

### All Three Backends
- [ ] Switch to EC2 backend → all operations work
- [ ] Switch to ECS backend → all operations work
- [ ] Switch to Lambda backend → all operations work

---

## Architecture Summary

```
                    ┌──────────────────────┐
                    │   S3 Static Website   │  ← Frontend (HTML/CSS/JS)
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
              │  ┌──────┐ ┌───────┐  │
              │  │login │ │music  │  │
              │  └──────┘ │+GSI   │  │
              │           │+LSI   │  │
              │           └───────┘  │
              │  ┌──────────────┐    │
              │  │subscriptions │    │
              │  └──────────────┘    │
              └──────────────────────┘
                         │
              ┌──────────▼───────────┐
              │  S3 (Private Bucket) │  ← Artist Images
              │  (Presigned URLs)    │     (Secure Access)
              └──────────────────────┘
```

---

## Important AWS Academy Notes

- **LabRole**: Always use `LabRole` — you CANNOT create new IAM roles
- **LabInstanceProfile**: Use this for EC2 instance IAM profile
- **Region**: Stick to `us-east-1`
- **Lab Timer**: Labs expire after ~4 hours. Click **Start Lab** again to continue
- **Persistence**: DynamoDB tables, S3 buckets, and ECR images persist between lab sessions. EC2 instances may stop — restart them if needed
- **No Elastic Beanstalk**: Explicitly prohibited in the assignment
- **Ports**: Must use port 80 (HTTP) or 443 (HTTPS) only

---

## IAM Troubleshooting (AWS Academy)

AWS Academy does NOT allow you to create or edit IAM roles. A pre-created role called **LabRole** is available. Here is exactly where to use it:

### Where LabRole / LabInstanceProfile Must Be Set

| Service | Where to set it | What to select |
|---------|----------------|----------------|
| **CloudShell** | Automatic — no action needed | (credentials are built-in) |
| **EC2** | Launch instance → Advanced details → IAM instance profile | **LabInstanceProfile** |
| **ECS** | Task definition → Task role | **LabRole** |
| **ECS** | Task definition → Task execution role | **LabRole** |
| **Lambda** | Create function → Permissions → Existing role | **LabRole** |
| **API Gateway** | No IAM role needed (uses Lambda's role) | — |

### Common Errors and Fixes

**Error**: `An error occurred (AccessDeniedException)` or `Unable to locate credentials`
- **On EC2**: You forgot to attach `LabInstanceProfile`. Go to EC2 Console → select instance → Actions → Security → Modify IAM role → select `LabInstanceProfile` → Save.
- **On ECS**: Task role is missing. Edit your task definition → set both Task role and Execution role to `LabRole`.
- **On Lambda**: Wrong execution role. Go to Lambda → Configuration → Permissions → Edit → select `LabRole`.

**Error**: `The security token included in the request is expired`
- Your AWS Academy lab session expired. Go back to the Learner Lab and click **Start Lab** again. Your resources (tables, buckets) are still there — you just need fresh credentials.

**Error**: `User: arn:aws:sts::... is not authorized to perform: iam:CreateRole`
- You are accidentally trying to create a role. NEVER create IAM roles in AWS Academy. Always choose **LabRole** from the existing roles dropdown.

**Error**: Presigned S3 URLs return `Access Denied`
- The service generating the URL (EC2/ECS/Lambda) doesn't have S3 access. Ensure LabRole/LabInstanceProfile is attached (see table above).
- Also ensure the S3 bucket name in your environment variable (`S3_BUCKET`) matches the actual bucket name.
