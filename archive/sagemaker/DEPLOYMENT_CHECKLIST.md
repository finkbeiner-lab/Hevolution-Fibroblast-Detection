# Pre-Deployment Checklist for SageMaker

Run this before deploying to ensure everything is ready:

```bash
python pre_deployment_check.py
```

## ✅ Code & Configuration

- [x] **Inference code** - `sagemaker_async_inference.py` has all required functions
- [x] **Cellpose API** - Uses `CellposeModel` (Cellpose 3.0+)
- [x] **BFloat16 disabled** - `use_bfloat16=False` to avoid CUDA errors
- [x] **eval() handling** - Handles both 3 and 4 return values
- [x] **Dockerfile** - All dependencies included with correct versions
- [x] **NumPy version** - Locked to 1.24.4 (compatible with PyTorch 2.0.1)
- [x] **Constraints file** - `constraints.txt` prevents NumPy upgrades
- [x] **Serve script** - Present and executable
- [x] **No hardcoded paths** - All paths use SageMaker environment variables

## ✅ Deployment Configuration

Current settings in `sagemaker_deploy.py`:
- **IAM Role**: `arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole`
- **Region**: `us-east-2`
- **S3 Bucket**: `YOUR_S3_BUCKET`
- **Instance Type**: `ml.g4dn.xlarge` (smallest GPU instance)
- **Endpoint Name**: `fibroblast-detection-endpoint`

**Verify these match your AWS setup before deploying!**

## ⚠️ Pre-Deployment Actions Required

### 1. Refresh AWS Credentials
```bash
./refresh_aws_credentials.sh
# Or manually:
export AWS_PROFILE=admin
aws sso login --profile admin
```

### 2. Verify S3 Bucket Exists
```bash
aws s3 ls s3://YOUR_S3_BUCKET --region us-east-2
# If it doesn't exist:
aws s3 mb s3://YOUR_S3_BUCKET --region us-east-2
```

### 3. Verify IAM Role Permissions
The SageMaker execution role (`SageMakerFibroblastRole`) needs:
- Access to S3 bucket
- Access to ECR (if pushing image)
- SageMaker execution permissions

Your SSO role needs:
- `iam:PassRole` permission for the SageMaker role
- `sagemaker:CreateModel`, `sagemaker:CreateEndpoint`, etc.

### 4. Docker Permissions (if building locally)
If you see Docker permission errors:
```bash
# Option 1: Add to docker group (recommended)
sudo usermod -aG docker $USER
newgrp docker

# Option 2: The deployment script will handle ECR push
# (Docker permissions only needed for local testing)
```

## 📋 Deployment Steps

1. **Run pre-deployment check:**
   ```bash
   python pre_deployment_check.py
   ```

2. **Refresh AWS credentials:**
   ```bash
   ./refresh_aws_credentials.sh
   ```

3. **Deploy:**
   ```bash
   python sagemaker_deploy.py
   ```

   This will:
   - Build Docker image (if not using `--skip-ecr`)
   - Push to ECR
   - Create model artifact
   - Upload to S3
   - Deploy endpoint

4. **Monitor deployment:**
   - Check CloudWatch logs if health check fails
   - Deployment takes 10-15 minutes

## 🔍 What Gets Deployed

### Docker Image
- Base: `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04`
- NumPy: 1.24.4 (locked)
- PyTorch: 2.0.1 with CUDA 11.8
- Cellpose: 3.0+ with BFloat16 disabled
- All dependencies verified during build

### Model Artifact
- Structure: `code/inference.py`, `requirements.txt`
- Created automatically during deployment
- Uploaded to: `s3://YOUR_S3_BUCKET/models/fibroblast-detection-model/`

### Endpoint Configuration
- Type: Asynchronous Inference
- Instance: `ml.g4dn.xlarge` (GPU required)
- Output: `s3://YOUR_S3_BUCKET/async-inference/output/`
- Max concurrent: 1 (GPU memory constraint)

## ✅ Everything Looks Good!

Your code is ready for deployment. The main things to do before deploying:

1. ✅ Refresh AWS credentials
2. ✅ Verify S3 bucket exists
3. ✅ Run deployment script

The deployment script will handle:
- Building and pushing Docker image
- Creating model artifact
- Uploading to S3
- Deploying endpoint

Good luck with your deployment! 🚀
