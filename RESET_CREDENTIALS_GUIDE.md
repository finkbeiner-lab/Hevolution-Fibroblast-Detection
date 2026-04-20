# Reset and Reconfigure AWS Credentials on EC2

Quick guide to completely reset and reconfigure AWS credentials.

## 🗑️ Quick Reset (Manual)

**On your EC2 instance, run:**

```bash
# Backup and remove old credentials
mkdir -p ~/.aws/backup
mv ~/.aws/credentials ~/.aws/backup/credentials.old 2>/dev/null
mv ~/.aws/config ~/.aws/backup/config.old 2>/dev/null

# Check if IAM role exists (better option)
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# If IAM role exists, test it:
aws sts get-caller-identity
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2

# If IAM role works, you're done! If not, configure credentials:
aws configure
```

## 📋 Step-by-Step Reset

### Step 1: Remove Old Credentials

```bash
# Backup old files (just in case)
mkdir -p ~/.aws/backup
cp ~/.aws/credentials ~/.aws/backup/credentials.backup 2>/dev/null
cp ~/.aws/config ~/.aws/backup/config.backup 2>/dev/null

# Remove old credentials
rm ~/.aws/credentials
# Keep config file (has region setting)
```

### Step 2: Check for IAM Role (Best Option)

```bash
# Check if IAM role is attached
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# If it shows a role name (e.g., "EC2-SageMaker-Role"):
#   → IAM role is attached, test it:
aws sts get-caller-identity
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2

# If it works, you're done! No need to configure credentials.
# If it shows "404 - Not Found", continue to Step 3.
```

### Step 3: Configure New Credentials

**Option A: Using Access Keys**

```bash
aws configure
# Enter:
# - AWS Access Key ID: [your access key]
# - AWS Secret Access Key: [your secret key]
# - Default region: us-east-2
# - Default output format: json
```

**Option B: Using SSO**

```bash
# If you have SSO configured
export AWS_PROFILE=your-profile-name
aws sso login
```

### Step 4: Test Credentials

```bash
# Test identity
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2

# Test SageMaker access
aws sagemaker describe-endpoint \
    --endpoint-name fibroblast-detection-endpoint \
    --region us-east-2
```

### Step 5: Restart Gradio Service

```bash
sudo systemctl restart gradio-app

# Check status
sudo systemctl status gradio-app

# View logs
sudo journalctl -u gradio-app -f
```

## 🔧 Using the Reset Script

I've created a script that does all of this automatically:

```bash
# Copy script to EC2 (from your local machine)
scp reset_aws_credentials.sh ubuntu@3.150.215.121:~/

# On EC2, run it
chmod +x ~/reset_aws_credentials.sh
~/reset_aws_credentials.sh
```

The script will:
1. ✅ Backup old credentials
2. ✅ Check for IAM role
3. ✅ Guide you through `aws configure` if needed
4. ✅ Test credentials
5. ✅ Restart Gradio service

## 🎯 Recommended: Use IAM Role

Instead of managing credentials, attach an IAM role to your EC2 instance:

1. **AWS Console** → EC2 → Select instance → Actions → Security → Modify IAM role
2. **Create role** (if needed):
   - IAM → Roles → Create role
   - Select "EC2"
   - Attach policies: `AmazonSageMakerFullAccess`, `AmazonS3FullAccess`
   - Name: `EC2-SageMaker-Role`
3. **Attach role** to your EC2 instance
4. **On EC2**, remove credentials file:
   ```bash
   rm ~/.aws/credentials
   aws sts get-caller-identity  # Should use IAM role
   sudo systemctl restart gradio-app
   ```

**Benefits:**
- ✅ Credentials never expire
- ✅ No manual configuration needed
- ✅ More secure
- ✅ Best practice

## ✅ Verification

After resetting, verify everything works:

```bash
# 1. Check credentials
aws sts get-caller-identity

# 2. Test S3
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2

# 3. Test Gradio
curl http://localhost:7860

# 4. Check service logs
sudo journalctl -u gradio-app -n 50
```

## 🐛 Troubleshooting

### "No credentials found"
- Run `aws configure` to set up credentials
- Or attach IAM role to EC2 instance

### "Access Denied"
- Check IAM permissions (S3 and SageMaker access)
- Verify bucket name: `fibroblast-detection-bucket`
- Verify region: `us-east-2`

### "ExpiredToken" still appears
- Wait a few seconds after configuring
- Restart service: `sudo systemctl restart gradio-app`
- Check credentials are saved: `cat ~/.aws/credentials`
