# Deploy Gradio Frontend on AWS EC2 with Domain

This guide shows how to host your Gradio app on AWS EC2 so users can access it via a domain name.

## Architecture

```
User → Domain Name → EC2 Instance → Gradio App → SageMaker Endpoint
```

---

## Step 1: Launch EC2 Instance

1. **Launch EC2 Instance:**
   - Instance type: `t3.medium` or `t3.large` (2-4GB RAM, no GPU needed)
   - OS: Ubuntu 22.04 LTS
   - Storage: 20GB minimum
   - Security Group: Allow HTTP (80), HTTPS (443), and SSH (22)

2. **Allocate Elastic IP** (for static IP address)
   - EC2 Console → Elastic IPs → Allocate Elastic IP address
   - Associate with your EC2 instance

---

## Step 2: Setup on EC2

SSH into your EC2 instance:

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

Install dependencies:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python and pip
sudo apt-get install -y python3 python3-pip python3-venv

# Install nginx (for reverse proxy)
sudo apt-get install -y nginx

# Install certbot (for SSL certificates)
sudo apt-get install -y certbot python3-certbot-nginx
```

---

## Step 3: Deploy Gradio App

```bash
# Create app directory
mkdir -p ~/fibroblast-app
cd ~/fibroblast-app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install gradio boto3 pillow

# Copy your Gradio-SageMaker.py file
# (Use scp from your local machine)
# scp Gradio-SageMaker.py ubuntu@your-ec2-ip:~/fibroblast-app/

# Or clone from git if you have it in a repo
# git clone <your-repo> .
# cp Gradio-SageMaker.py ~/fibroblast-app/

# Configure AWS credentials (if not using IAM role)
aws configure
```

---

## Step 4: Create Systemd Service

Create a service file to keep Gradio running automatically:

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
Environment="GRADIO_SERVER_NAME=127.0.0.1"
Environment="GRADIO_SERVER_PORT=7860"
ExecStart=/home/ubuntu/fibroblast-app/venv/bin/python /home/ubuntu/fibroblast-app/Gradio-SageMaker.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gradio-app
sudo systemctl start gradio-app
sudo systemctl status gradio-app
```

---

## Step 5: Configure Nginx Reverse Proxy

Create nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/gradio
```

Add this configuration (replace `your-domain.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/gradio /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

---

## Step 6: Setup Domain Name

1. **Register Domain** (Route 53, Namecheap, GoDaddy, etc.)

2. **Point Domain to EC2:**
   - Get your Elastic IP address from EC2 Console
   - Go to your domain registrar's DNS settings
   - Add A record:
     - **Type:** A
     - **Name:** @ (or leave blank for root domain) or `www` for subdomain
     - **Value:** Your Elastic IP address
     - **TTL:** 300 (or default)

3. **Wait for DNS propagation** (5-30 minutes, can take up to 48 hours)

Verify DNS is working:
```bash
dig your-domain.com
# Should return your Elastic IP
```

---

## Step 7: Setup SSL Certificate (HTTPS)

Once your domain points to EC2, get a free SSL certificate:

```bash
# Get SSL certificate from Let's Encrypt
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Follow the prompts:
# - Enter email address
# - Agree to terms
# - Choose whether to redirect HTTP to HTTPS (recommended: Yes)
```

Certbot will automatically:
- Get the certificate
- Configure nginx for HTTPS
- Set up auto-renewal

Your app is now accessible at: `https://your-domain.com`

---

## IAM Permissions for EC2

Your EC2 instance needs IAM permissions to call SageMaker:

1. **Create IAM Role:**
   - Go to IAM Console → Roles → Create Role
   - Select "EC2" as the service
   - Attach policies:
     - `AmazonSageMakerFullAccess` (or create scoped policy)
     - `AmazonS3FullAccess` (or scoped to your bucket only)

2. **Attach Role to EC2:**
   - EC2 Console → Select your instance → Actions → Security → Modify IAM role
   - Select the role you created
   - Save

3. **Or use AWS credentials:**
   ```bash
   aws configure
   ```

---

## Environment Variables

The systemd service already sets these, but you can also set them manually:

```bash
export SAGEMAKER_ENDPOINT_NAME="fibroblast-detection-endpoint"
export AWS_REGION="us-east-2"
export S3_BUCKET="YOUR_S3_BUCKET"
export GRADIO_SERVER_NAME="127.0.0.1"
export GRADIO_SERVER_PORT="7860"
```

---

## Cost Estimate

- **EC2 t3.medium:** ~$30/month (24/7)
- **EC2 t3.large:** ~$60/month (24/7)
- **Elastic IP:** Free (if attached to instance)
- **Domain:** ~$10-15/year
- **SSL Certificate:** Free (Let's Encrypt)

**Total: ~$30-60/month**

---

## Troubleshooting

### Gradio not accessible

```bash
# Check if Gradio service is running
sudo systemctl status gradio-app

# Check logs
sudo journalctl -u gradio-app -f

# Check if nginx is running
sudo systemctl status nginx

# Check nginx logs
sudo tail -f /var/log/nginx/error.log

# Test Gradio directly (should work on port 7860)
curl http://localhost:7860
```

### Security Group Issues

- Ensure security group allows:
  - Port 22 (SSH)
  - Port 80 (HTTP)
  - Port 443 (HTTPS)
- Source: `0.0.0.0/0` for HTTP/HTTPS, your IP for SSH

### Domain not resolving

```bash
# Check DNS
dig your-domain.com
nslookup your-domain.com

# Verify Elastic IP is attached
# EC2 Console → Elastic IPs → Check association
```

### SSL certificate issues

```bash
# Check certificates
sudo certbot certificates

# Test renewal
sudo certbot renew --dry-run

# If domain doesn't point to EC2, certbot will fail
# Fix DNS first, then run certbot again
```

### Service won't start

```bash
# Check service status
sudo systemctl status gradio-app

# Check if file exists
ls -la /home/ubuntu/fibroblast-app/Gradio-SageMaker.py

# Test manually
cd /home/ubuntu/fibroblast-app
source venv/bin/activate
python Gradio-SageMaker.py
```

---

## Quick Setup Script

Save this as `setup-gradio-ec2.sh` on your EC2 instance:

```bash
#!/bin/bash

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Setup app
mkdir -p ~/fibroblast-app
cd ~/fibroblast-app
python3 -m venv venv
source venv/bin/activate
pip install gradio boto3 pillow

echo "Setup complete! Now:"
echo "1. Copy Gradio-SageMaker.py to ~/fibroblast-app/"
echo "2. Configure systemd service (Step 4)"
echo "3. Setup nginx (Step 5)"
echo "4. Point domain to this EC2 instance (Step 6)"
echo "5. Setup SSL certificate (Step 7)"
```

Make it executable and run:
```bash
chmod +x setup-gradio-ec2.sh
./setup-gradio-ec2.sh
```

---

## Next Steps

1. ✅ Deploy Gradio app to EC2
2. ✅ Configure domain name
3. ✅ Setup SSL certificate
4. ✅ Test end-to-end: Upload image → SageMaker processes → Results displayed

Your users can now access: `https://your-domain.com`

---

## Maintenance

### Update Gradio App

```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@your-ec2-ip

# Stop service
sudo systemctl stop gradio-app

# Update code
cd ~/fibroblast-app
# Copy new Gradio-SageMaker.py or pull from git

# Restart service
sudo systemctl start gradio-app
```

### View Logs

```bash
# Gradio service logs
sudo journalctl -u gradio-app -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart Services

```bash
# Restart Gradio
sudo systemctl restart gradio-app

# Restart Nginx
sudo systemctl restart nginx
```
