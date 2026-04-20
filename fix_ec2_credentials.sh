#!/bin/bash
# Quick script to fix AWS credentials on EC2

echo "=========================================="
echo "Fixing AWS Credentials on EC2"
echo "=========================================="
echo ""

# Check current identity
echo "Current AWS identity:"
aws sts get-caller-identity 2>&1 || echo "No credentials found"
echo ""

# Option 1: Check if IAM role is attached
echo "Checking for IAM role..."
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
if [ -n "$INSTANCE_ID" ]; then
    echo "Instance ID: $INSTANCE_ID"
    ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
    if [ -n "$ROLE" ]; then
        echo "✅ IAM Role found: $ROLE"
        echo ""
        echo "The instance has an IAM role, but credentials may need refresh."
        echo "Trying to refresh..."
        # Force refresh by getting new credentials
        curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE > /dev/null
        sleep 2
        echo "Testing credentials..."
        aws sts get-caller-identity && echo "✅ Credentials working!" || echo "❌ Still not working"
    else
        echo "❌ No IAM role attached to this instance"
        echo ""
        echo "RECOMMENDED: Attach an IAM role via AWS Console:"
        echo "1. EC2 Console → Select instance → Actions → Security → Modify IAM role"
        echo "2. Create/select role with SageMaker and S3 permissions"
        echo ""
    fi
else
    echo "Could not detect instance ID"
fi

echo ""
echo "=========================================="
echo "Option 2: Configure AWS Credentials"
echo "=========================================="
echo ""
echo "If you have AWS Access Keys, run:"
echo "  aws configure"
echo ""
echo "Or if using SSO:"
echo "  export AWS_PROFILE=your-profile"
echo "  aws sso login"
echo ""
echo "Then test:"
echo "  aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2"
echo ""
