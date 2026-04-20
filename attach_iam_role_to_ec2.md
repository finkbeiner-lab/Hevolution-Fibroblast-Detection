# Attach SageMakerFibroblastRole to EC2 Instance

You already have the IAM role `SageMakerFibroblastRole`. Here's how to attach it to your EC2 instance.

## 🖥️ Method 1: AWS Console (Easiest)

1. **Go to EC2 Console:**
   - AWS Console → EC2 → Instances

2. **Select your instance:**
   - Find the instance with IP `3.150.215.121` (or your instance)
   - Click the checkbox next to it

3. **Attach IAM role:**
   - Click **Actions** → **Security** → **Modify IAM role**
   - In the dropdown, select **SageMakerFibroblastRole**
   - Click **Update IAM role**

4. **Wait 10-20 seconds** for the role to be attached

5. **On EC2, test it:**
   ```bash
   # Remove any existing credentials (they override IAM role)
   rm ~/.aws/credentials
   unset AWS_PROFILE
   
   # Test IAM role
   aws sts get-caller-identity
   # Should show the IAM role ARN, not your user
   
   # Test S3 access
   aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2
   
   # Restart Gradio
   sudo systemctl restart gradio-app
   ```

## 💻 Method 2: AWS CLI (From Your Local Machine)

**From your local machine (with valid credentials):**

```bash
# Get your instance ID first
# Option 1: From EC2 Console (Instance ID column)
# Option 2: From EC2 instance itself:
#   curl http://169.254.169.254/latest/meta-data/instance-id

# Attach IAM role (replace i-xxxxxxxxx with your instance ID)
aws ec2 associate-iam-instance-profile \
    --instance-id i-xxxxxxxxx \
    --iam-instance-profile Name=SageMakerFibroblastRole \
    --region us-east-2
```

**Note:** You need to create an instance profile first if it doesn't exist:

```bash
# Create instance profile (if needed)
aws iam create-instance-profile \
    --instance-profile-name SageMakerFibroblastRole \
    --region us-east-2

# Add role to instance profile
aws iam add-role-to-instance-profile \
    --instance-profile-name SageMakerFibroblastRole \
    --role-name SageMakerFibroblastRole \
    --region us-east-2

# Then attach to EC2
aws ec2 associate-iam-instance-profile \
    --instance-id i-xxxxxxxxx \
    --iam-instance-profile Name=SageMakerFibroblastRole \
    --region us-east-2
```

## ✅ Verify It's Attached

**On EC2 instance, run:**

```bash
# Check if IAM role is attached
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Should show: SageMakerFibroblastRole (or similar)

# Test credentials
aws sts get-caller-identity
# Should show ARN like: arn:aws:sts::ACCOUNT:assumed-role/SageMakerFibroblastRole/i-xxxxx

# Test S3
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2
```

## 🔧 After Attaching Role

**On EC2, clean up old credentials:**

```bash
# Remove SSO profile from environment
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE

# Remove or backup credentials file (IAM role will be used automatically)
mv ~/.aws/credentials ~/.aws/credentials.backup 2>/dev/null

# Remove SSO cache
rm -rf ~/.aws/sso/cache/* 2>/dev/null

# Test IAM role works
aws sts get-caller-identity

# Restart Gradio service
sudo systemctl restart gradio-app

# Check logs
sudo journalctl -u gradio-app -f
```

## 🎯 Quick One-Liner (After Attaching Role)

**On EC2, after you've attached the role via Console:**

```bash
unset AWS_PROFILE AWS_DEFAULT_PROFILE && \
rm ~/.aws/credentials 2>/dev/null && \
aws sts get-caller-identity && \
aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2 && \
sudo systemctl restart gradio-app
```

## 📋 Step-by-Step Summary

1. ✅ **AWS Console** → EC2 → Select instance → Actions → Security → Modify IAM role
2. ✅ **Select** `SageMakerFibroblastRole` → Update IAM role
3. ✅ **On EC2**: `unset AWS_PROFILE && rm ~/.aws/credentials`
4. ✅ **Test**: `aws sts get-caller-identity` (should show role ARN)
5. ✅ **Restart**: `sudo systemctl restart gradio-app`

That's it! The IAM role credentials never expire and work automatically. 🎉
