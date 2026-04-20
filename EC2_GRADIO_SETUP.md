# EC2 Gradio Setup Guide

Quick guide to deploy and use `Gradio-SageMaker.py` on EC2 with your deployed SageMaker endpoint.

## ✅ Prerequisites

1. **SageMaker Endpoint Deployed** ✅ (You've done this!)
   - Endpoint: `fibroblast-detection-endpoint`
   - Region: `us-east-2`

2. **EC2 Instance Running**
   - Ubuntu 22.04 LTS recommended
   - Instance type: `t3.medium` or `t3.large` (no GPU needed for Gradio)
   - Security Group: Allow inbound on port 7860 (or 80/443 if using nginx)

## 🚀 Quick Setup on EC2

### Step 1: SSH into EC2

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### Step 2: Install Dependencies

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python and pip
sudo apt-get install -y python3 python3-pip python3-venv

# Create app directory
mkdir -p ~/fibroblast-app
cd ~/fibroblast-app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install gradio>=4.0.0 boto3>=1.26.0 Pillow>=9.0.0
```

### Step 3: Copy Gradio Script

Copy `Gradio-SageMaker.py` to your EC2 instance:

**From your local machine:**
```bash
scp Gradio-SageMaker.py ubuntu@your-ec2-ip:~/fibroblast-app/
```

**Or clone from git if you have a repo:**
```bash
# On EC2
cd ~/fibroblast-app
git clone <your-repo-url> .
```

### Step 4: Configure AWS Credentials

**Option A: Use IAM Role (Recommended)**
1. Create IAM role with permissions:
   - `AmazonSageMakerFullAccess` (or scoped to your endpoint)
   - `AmazonS3FullAccess` (or scoped to `YOUR_S3_BUCKET`)
2. Attach role to EC2 instance:
   - EC2 Console → Select instance → Actions → Security → Modify IAM role

**Option B: Use AWS Credentials**
```bash
# On EC2
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and region (us-east-2)
```

### Step 5: Set Environment Variables (Optional)

The script uses these defaults, but you can override:
```bash
export SAGEMAKER_ENDPOINT_NAME="fibroblast-detection-endpoint"
export AWS_REGION="us-east-2"
export S3_BUCKET="YOUR_S3_BUCKET"
export GRADIO_SERVER_NAME="0.0.0.0"  # Listen on all interfaces
export GRADIO_SERVER_PORT="7860"
```

### Step 6: Run Gradio App

**Test run:**
```bash
cd ~/fibroblast-app
source venv/bin/activate
python Gradio-SageMaker.py
```

You should see:
```
Running on local URL:  http://0.0.0.0:7860
```

**Access from browser:**
- `http://your-ec2-ip:7860`

## 🔧 Run as a Service (Auto-start on boot)

Create a systemd service to keep Gradio running:

```bash
sudo nano /etc/systemd/system/gradio-app.service
```

Add this content:
```ini
[Unit]
Description=Gradio Fibroblast Detection App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/fibroblast-app
Environment="PATH=/home/ubuntu/fibroblast-app/venv/bin"
Environment="SAGEMAKER_ENDPOINT_NAME=fibroblast-detection-endpoint"
Environment="AWS_REGION=us-east-2"
Environment="S3_BUCKET=YOUR_S3_BUCKET"
Environment="GRADIO_SERVER_NAME=0.0.0.0"
Environment="GRADIO_SERVER_PORT=7860"
ExecStart=/home/ubuntu/fibroblast-app/venv/bin/python /home/ubuntu/fibroblast-app/Gradio-SageMaker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gradio-app
sudo systemctl start gradio-app

# Check status
sudo systemctl status gradio-app

# View logs
sudo journalctl -u gradio-app -f
```

## 🔒 Security Group Configuration

Make sure your EC2 security group allows inbound traffic:

**For direct access:**
- Port 7860 from your IP or 0.0.0.0/0 (less secure)

**For production (with nginx):**
- Port 80 (HTTP) from 0.0.0.0/0
- Port 443 (HTTPS) from 0.0.0.0/0
- Port 22 (SSH) from your IP only

## ✅ Verify It Works

1. **Check endpoint is accessible:**
   ```bash
   # On EC2
   aws sagemaker describe-endpoint --endpoint-name fibroblast-detection-endpoint --region us-east-2
   ```

2. **Test S3 access:**
   ```bash
   aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
   ```

3. **Access Gradio UI:**
   - Open browser: `http://your-ec2-ip:7860`
   - Upload an image
   - Click "Run Detection"
   - Wait for results (may take 30-60 seconds)

## 🐛 Troubleshooting

### "Endpoint not found" error
- Verify endpoint name: `fibroblast-detection-endpoint`
- Check region: `us-east-2`
- Verify IAM permissions allow SageMaker access

### "Access Denied" to S3
- Check IAM role has S3 permissions
- Verify bucket name: `YOUR_S3_BUCKET`
- Check bucket exists in `us-east-2`

### Gradio not accessible from browser
- Check security group allows port 7860
- Verify EC2 instance is running
- Check service is running: `sudo systemctl status gradio-app`

### Timeout errors
- SageMaker async inference can take 1-5 minutes
- Check CloudWatch logs for endpoint issues
- Verify endpoint is "InService"

## 📊 Current Configuration

Your Gradio app is configured to use:
- **Endpoint:** `fibroblast-detection-endpoint`
- **Region:** `us-east-2`
- **S3 Bucket:** `YOUR_S3_BUCKET`
- **Port:** 7860

All set! You can now upload images through the Gradio interface. 🎉
