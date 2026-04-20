# Fix AWS Credentials on EC2

Your EC2 instance has expired AWS credentials. Here are two solutions:

## 🔧 Solution 1: Use IAM Role (Recommended - Credentials Never Expire)

This is the best solution for production. The EC2 instance will automatically use the IAM role credentials, which never expire.

### Steps:

1. **Create IAM Role** (if it doesn't exist):
   - Go to AWS Console → IAM → Roles → Create Role
   - Select "EC2" as the service
   - Attach policies:
     - `AmazonSageMakerFullAccess` (or create scoped policy)
     - `AmazonS3FullAccess` (or scoped to `YOUR_S3_BUCKET` only)
   - Name it: `EC2-SageMaker-Role` (or similar)
   - Create role

2. **Attach Role to EC2 Instance**:
   ```bash
   # Via AWS Console:
   # EC2 → Select instance → Actions → Security → Modify IAM role
   # Select your role → Update IAM role
   ```

   Or via CLI:
   ```bash
   aws ec2 associate-iam-instance-profile \
       --instance-id i-xxxxxxxxx \
       --iam-instance-profile Name=EC2-SageMaker-Role
   ```

3. **Restart Gradio Service**:
   ```bash
   ssh ubuntu@YOUR_EC2_IP
   sudo systemctl restart gradio-app
   ```

4. **Verify**:
   ```bash
   # On EC2, test credentials
   aws sts get-caller-identity
   # Should show the IAM role, not your user
   ```

---

## 🔧 Solution 2: Refresh SSO Credentials (Temporary Fix)

If you're using AWS SSO, refresh the credentials:

### Steps:

1. **SSH into EC2**:
   ```bash
   ssh -i your-key.pem ubuntu@YOUR_EC2_IP
   ```

2. **Refresh SSO Credentials**:
   ```bash
   # If using SSO profile
   export AWS_PROFILE=your-profile-name
   aws sso login
   
   # Or configure credentials
   aws configure
   # Enter Access Key ID, Secret Access Key, Region (us-east-2)
   ```

3. **Test Credentials**:
   ```bash
   aws sts get-caller-identity
   aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
   ```

4. **Restart Gradio Service**:
   ```bash
   sudo systemctl restart gradio-app
   ```

5. **Check Logs**:
   ```bash
   sudo journalctl -u gradio-app -f
   ```

**Note:** SSO credentials expire after a few hours. You'll need to refresh them periodically, or use Solution 1 (IAM role).

---

## 🔧 Solution 3: Use AWS Credentials File (Alternative)

If you have long-term access keys:

1. **SSH into EC2**:
   ```bash
   ssh ubuntu@YOUR_EC2_IP
   ```

2. **Create credentials file**:
   ```bash
   mkdir -p ~/.aws
   nano ~/.aws/credentials
   ```

   Add:
   ```ini
   [default]
   aws_access_key_id = YOUR_ACCESS_KEY_ID
   aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
   region = us-east-2
   ```

3. **Set permissions**:
   ```bash
   chmod 600 ~/.aws/credentials
   ```

4. **Restart service**:
   ```bash
   sudo systemctl restart gradio-app
   ```

---

## ✅ Verify It's Working

After applying a solution:

1. **Test from EC2**:
   ```bash
   # Check credentials
   aws sts get-caller-identity
   
   # Test S3 access
   aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
   
   # Test SageMaker access
   aws sagemaker describe-endpoint \
       --endpoint-name fibroblast-detection-endpoint \
       --region us-east-2
   ```

2. **Test Gradio App**:
   - Open: `http://YOUR_EC2_IP:7860`
   - Upload an image
   - Click "Run Detection"
   - Should work without credential errors

3. **Check Service Logs**:
   ```bash
   sudo journalctl -u gradio-app -n 50
   ```
   Should not show "ExpiredToken" errors.

---

## 🎯 Recommended: IAM Role

**Why IAM Role is Better:**
- ✅ Credentials never expire
- ✅ More secure (no keys stored on instance)
- ✅ Automatically rotated
- ✅ No manual intervention needed
- ✅ Best practice for EC2

**IAM Role Permissions Needed:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_S3_BUCKET",
        "arn:aws:s3:::YOUR_S3_BUCKET/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sagemaker:InvokeEndpointAsync",
        "sagemaker:DescribeEndpoint"
      ],
      "Resource": "arn:aws:sagemaker:us-east-2:*:endpoint/fibroblast-detection-endpoint"
    }
  ]
}
```

---

## 🐛 Troubleshooting

### "No credentials found"
- Check IAM role is attached: `aws sts get-caller-identity`
- Check credentials file exists: `ls -la ~/.aws/credentials`

### "ExpiredToken" still appears
- Wait a few seconds after refreshing credentials
- Restart the service: `sudo systemctl restart gradio-app`
- Check service is using updated credentials: `sudo journalctl -u gradio-app -f`

### Service won't start
- Check logs: `sudo journalctl -u gradio-app -n 100`
- Verify Python environment: `source ~/fibroblast-app/venv/bin/activate && python --version`
- Check file permissions: `ls -la ~/fibroblast-app/Gradio-SageMaker.py`
