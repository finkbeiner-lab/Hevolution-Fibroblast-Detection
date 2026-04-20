# Complete IAM Role Setup for EC2

Your `SageMakerFibroblastRole` currently only trusts SageMaker. To use it on EC2, you need to:

1. ✅ Update trust policy to include EC2
2. ✅ Create instance profile
3. ✅ Attach to EC2 instance

## Step 1: Update Trust Policy

The role needs to trust both SageMaker AND EC2.

### Option A: AWS Console

1. **IAM Console** → Roles → `SageMakerFibroblastRole`
2. Click **"Trust relationships"** tab
3. Click **"Edit trust policy"**
4. Replace with:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": [
                    "sagemaker.amazonaws.com",
                    "ec2.amazonaws.com"
                ]
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

5. Click **"Update policy"**

### Option B: AWS CLI

**From your local machine:**

```bash
# Update trust policy
aws iam update-assume-role-policy \
    --role-name SageMakerFibroblastRole \
    --policy-document file://update_trust_policy.json
```

Or use the script:
```bash
chmod +x update_role_trust_policy.sh
./update_role_trust_policy.sh
```

## Step 2: Create Instance Profile

### Option A: AWS Console

1. **IAM Console** → Instance profiles → **Create instance profile**
2. Name: `SageMakerFibroblastRole`
3. Click **Create instance profile**
4. Click on the instance profile → **Add role**
5. Select `SageMakerFibroblastRole` → **Add role**

### Option B: AWS CLI

```bash
# Create instance profile
aws iam create-instance-profile \
    --instance-profile-name SageMakerFibroblastRole

# Add role to instance profile
aws iam add-role-to-instance-profile \
    --instance-profile-name SageMakerFibroblastRole \
    --role-name SageMakerFibroblastRole
```

Or use the script:
```bash
chmod +x create_instance_profile.sh
./create_instance_profile.sh
```

## Step 3: Attach to EC2 Instance

### Option A: AWS Console

1. **EC2 Console** → Instances → Select your instance
2. **Actions** → **Security** → **Modify IAM role**
3. You should now see `SageMakerFibroblastRole` in the dropdown
4. Select it → **Update IAM role**

### Option B: AWS CLI

```bash
# Get your instance ID (from EC2 Console)
INSTANCE_ID="i-xxxxxxxxx"  # Replace with your instance ID

# Attach instance profile
aws ec2 associate-iam-instance-profile \
    --instance-id $INSTANCE_ID \
    --iam-instance-profile Name=SageMakerFibroblastRole \
    --region us-east-2
```

## Step 4: On EC2, Clean Up and Test

**On your EC2 instance:**

```bash
# Remove SSO profile
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE

# Remove old credentials
rm ~/.aws/credentials 2>/dev/null

# Clear SSO cache
rm -rf ~/.aws/sso/cache/* 2>/dev/null

# Wait for IAM role to be available
sleep 10

# Test IAM role
aws sts get-caller-identity
# Should show: arn:aws:sts::ACCOUNT:assumed-role/SageMakerFibroblastRole/...

# Test S3
aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2

# Restart Gradio
sudo systemctl restart gradio-app

# Check logs
sudo journalctl -u gradio-app -f
```

## ✅ Complete Checklist

- [ ] Trust policy updated to include `ec2.amazonaws.com`
- [ ] Instance profile `SageMakerFibroblastRole` created
- [ ] Role added to instance profile
- [ ] Instance profile attached to EC2 instance
- [ ] On EC2: Removed old credentials
- [ ] On EC2: `aws sts get-caller-identity` shows role ARN
- [ ] On EC2: S3 access works
- [ ] Gradio service restarted
- [ ] No "ExpiredToken" errors in logs

## 🎯 Quick Summary

**The Problem:**
- Role only trusted SageMaker
- No instance profile existed
- Role couldn't be attached to EC2

**The Solution:**
1. Update trust policy: Add `ec2.amazonaws.com`
2. Create instance profile: `SageMakerFibroblastRole`
3. Add role to instance profile
4. Attach to EC2 instance
5. Remove old credentials on EC2

After these steps, the IAM role will work automatically on EC2! 🎉
