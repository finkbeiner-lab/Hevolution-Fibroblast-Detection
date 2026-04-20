# Quick Start Guide: AWS Deployment

## Option 1: SageMaker Asynchronous Inference (Recommended)

### Prerequisites
```bash
# Install dependencies
pip install sagemaker boto3

# Configure AWS CLI
aws configure
```

### Step 1: Update Configuration
Edit `sagemaker_deploy.py`:
- Replace `YOUR_ACCOUNT_ID` with your AWS account ID
- Update `ROLE` with your IAM role ARN
- Set `BUCKET_NAME` to your S3 bucket
- Choose your `REGION`

### Step 2: Create S3 Bucket
```bash
aws s3 mb s3://your-sagemaker-bucket
```

### Step 3: Create IAM Role
1. Go to IAM Console → Roles → Create Role
2. Select "SageMaker" as service
3. Attach policies:
   - `AmazonSageMakerFullAccess`
   - `AmazonS3FullAccess` (or scoped)
4. Note the Role ARN

### Step 4: Build and Push Docker Image (Recommended)
```bash
# Create ECR repository
aws ecr create-repository --repository-name fibroblast-detection --region us-east-1

# Get login
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t fibroblast-detection:latest .
docker tag fibroblast-detection:latest \
    YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/fibroblast-detection:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/fibroblast-detection:latest
```

### Step 5: Deploy
```bash
python sagemaker_deploy.py
```

### Step 6: Test
```bash
# Update test_sagemaker_async.py with your endpoint name and bucket
python test_sagemaker_async.py path/to/image.jpg
```

---

## Option 2: Local Docker (Testing)

### Build and Run
```bash
# Build image
docker build -t fibroblast-detection:latest .

# Run with GPU
docker run -d -p 7860:7860 --gpus all fibroblast-detection:latest

# Access at http://localhost:7860
```

### Using Docker Compose
```bash
docker-compose up -d
```

---

## Option 3: EC2 Deployment

### Launch EC2 Instance
1. Choose `g4dn.xlarge` or larger (GPU instance)
2. Use Deep Learning AMI (Ubuntu) or Amazon Linux 2
3. Configure security group: Allow port 7860

### On EC2 Instance
```bash
# Install Docker
sudo yum install docker -y  # Amazon Linux
# OR
sudo apt-get install docker.io -y  # Ubuntu

# Install NVIDIA Docker runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Clone your repo or copy files
git clone <your-repo>
cd <your-repo>

# Build and run
docker build -t fibroblast-detection:latest .
docker run -d -p 7860:7860 --gpus all fibroblast-detection:latest
```

### Access
- Public IP: `http://<EC2_PUBLIC_IP>:7860`
- Or use Elastic IP for static address

---

## Cost Estimates

| Option | Cost/Hour | Monthly (24/7) | Best For |
|--------|-----------|----------------|----------|
| SageMaker Async | ~$0.736 | ~$80* | Production |
| EC2 g4dn.xlarge | ~$0.526 | ~$380 | Development |
| ECS Fargate GPU | ~$0.60 | ~$430 | Container orchestration |

*SageMaker Async: Pay per inference, not per hour. Estimate based on 100 requests/day.

---

## Troubleshooting

### GPU Not Available
- Ensure instance type has GPU (`ml.g4dn.xlarge`, `g4dn.xlarge`)
- Check NVIDIA drivers: `nvidia-smi`
- Verify Docker GPU support: `docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi`

### Out of Memory
- Increase instance size
- Reduce image size before processing
- Use batch processing for multiple images

### Timeout Issues
- Use Async Inference (no timeout limit)
- Or increase timeout in real-time endpoint config

### Model Loading Slow
- Pre-warm endpoint
- Use model caching
- Consider smaller model variant

---

## Next Steps

1. **Monitor**: Set up CloudWatch alarms
2. **Scale**: Configure auto-scaling for high traffic
3. **Security**: Use VPC endpoints, IAM policies
4. **Cost Optimization**: Use Spot instances for dev, Reserved for prod

For detailed information, see [AWS_DEPLOYMENT_GUIDE.md](./AWS_DEPLOYMENT_GUIDE.md)
