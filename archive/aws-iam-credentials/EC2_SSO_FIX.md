# Fix AWS SSO on EC2 (No Browser Access)

When you run `aws configure sso` on EC2, it tries to open a browser which you can't access. Here are solutions:

## 🚫 Problem

EC2 instances can't open browsers, so `aws configure sso` doesn't work directly.

## ✅ Solution 1: Use Access Keys Instead (Easiest)

**On EC2, use regular access keys:**

```bash
# Remove SSO config if it exists
rm ~/.aws/config  # or edit it to remove SSO section

# Configure with access keys
aws configure
# Enter:
# - AWS Access Key ID: [your access key]
# - AWS Secret Access Key: [your secret key]
# - Default region: us-east-2
# - Default output format: json
```

**To get Access Keys:**
1. AWS Console → IAM → Users → Your User → Security Credentials
2. Create Access Key
3. Copy Access Key ID and Secret Access Key

## ✅ Solution 2: Copy SSO Credentials from Local Machine

**Step 1: On your LOCAL machine, login with SSO:**

```bash
aws sso login --profile your-profile
```

**Step 2: Copy credentials to EC2:**

```bash
# From your local machine
scp ~/.aws/credentials ubuntu@YOUR_EC2_IP:~/.aws/
scp ~/.aws/config ubuntu@YOUR_EC2_IP:~/.aws/
```

**Step 3: On EC2, test:**

```bash
aws sts get-caller-identity
aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
```

**⚠️ Note:** SSO credentials expire after a few hours, so you'll need to repeat this.

## ✅ Solution 3: Manual SSO Login URL

**Step 1: On your LOCAL machine, get the SSO login URL:**

```bash
# Check your SSO config
cat ~/.aws/config | grep sso_start_url

# Or run (it will show the URL before trying to open browser)
aws sso login --profile your-profile 2>&1 | grep -i "https://"
```

**Step 2: Open that URL in YOUR browser (on your local machine)**

**Step 3: After login, copy the credentials as in Solution 2**

## ✅ Solution 4: Use IAM Role (BEST - Recommended)

Instead of managing credentials, attach an IAM role to EC2:

**Step 1: Create IAM Role (if needed):**
- AWS Console → IAM → Roles → Create Role
- Select "EC2" as service
- Attach policies:
  - `AmazonSageMakerFullAccess`
  - `AmazonS3FullAccess`
- Name: `EC2-SageMaker-Role`
- Create role

**Step 2: Attach to EC2:**
- EC2 Console → Select instance → Actions → Security → Modify IAM role
- Select the role → Update

**Step 3: On EC2, remove credentials file:**

```bash
# Remove any existing credentials (they override IAM role)
rm ~/.aws/credentials

# Test IAM role
aws sts get-caller-identity
# Should show the IAM role ARN, not your user

# Test S3
aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
```

**✅ Benefits:**
- Credentials never expire
- No manual configuration
- More secure
- Best practice

## 🔧 Quick Fix Script

I've created a script to help:

```bash
# Copy to EC2
scp configure_aws_ec2.sh ubuntu@YOUR_EC2_IP:~/

# On EC2, run it
chmod +x ~/configure_aws_ec2.sh
~/configure_aws_ec2.sh
```

## 📋 Recommended Approach

**For production (EC2):**
1. ✅ Attach IAM role to EC2 instance
2. ✅ Remove `~/.aws/credentials` file
3. ✅ IAM role credentials work automatically

**For development (local):**
- Use SSO: `aws sso login --profile your-profile`

## 🐛 Troubleshooting

### "No credentials found" after removing credentials
- Check IAM role is attached: `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/`
- If no role, configure access keys: `aws configure`

### SSO credentials expire quickly
- This is normal - SSO tokens expire after a few hours
- Use IAM role instead (never expires)
- Or use access keys (longer expiration)

### "Access Denied" with IAM role
- Check IAM role has correct policies attached
- Verify policies allow S3 and SageMaker access
- Check resource ARNs in policies match your resources
