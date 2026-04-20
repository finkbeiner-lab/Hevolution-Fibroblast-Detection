#!/bin/bash
# Check and fix AWS credentials on EC2

echo "=========================================="
echo "Checking AWS Credentials"
echo "=========================================="
echo ""

# Test current credentials
echo "Testing current credentials..."
if aws sts get-caller-identity 2>/dev/null; then
    echo "✅ Credentials are valid!"
    echo ""
    echo "Testing S3 access..."
    if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
        echo "✅ S3 access working!"
        exit 0
    else
        echo "❌ S3 access failed (but credentials are valid)"
        echo "   Check IAM permissions for S3 access"
        exit 1
    fi
else
    echo "❌ Credentials are expired or invalid"
    echo ""
fi

echo ""
echo "=========================================="
echo "Checking for IAM Role"
echo "=========================================="
echo ""

# Check if IAM role is attached
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
if [ -n "$INSTANCE_ID" ]; then
    echo "Instance ID: $INSTANCE_ID"
    ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
    if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
        echo "✅ IAM Role found: $ROLE"
        echo ""
        echo "The instance has an IAM role. The expired credentials in ~/.aws/credentials"
        echo "are overriding the IAM role credentials."
        echo ""
        echo "SOLUTION: Remove or rename the expired credentials file:"
        echo "  mv ~/.aws/credentials ~/.aws/credentials.backup"
        echo ""
        echo "Then test again:"
        echo "  aws sts get-caller-identity"
        echo "  aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2"
    else
        echo "❌ No IAM role attached to this instance"
        echo ""
        echo "You need to either:"
        echo "1. Update the credentials in ~/.aws/credentials with new access keys"
        echo "2. Attach an IAM role to the EC2 instance (recommended)"
    fi
else
    echo "Could not detect instance ID"
fi

echo ""
echo "=========================================="
echo "Current Credential Files"
echo "=========================================="
echo ""

if [ -f ~/.aws/credentials ]; then
    echo "~/.aws/credentials exists"
    echo "Last modified: $(stat -c %y ~/.aws/credentials 2>/dev/null || stat -f %Sm ~/.aws/credentials 2>/dev/null)"
    echo ""
    echo "To view (first few lines):"
    echo "  head -5 ~/.aws/credentials"
fi

if [ -f ~/.aws/config ]; then
    echo "~/.aws/config exists"
fi

echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "Option 1: If you have an IAM role attached, remove expired credentials:"
echo "  mv ~/.aws/credentials ~/.aws/credentials.backup"
echo ""
echo "Option 2: Update credentials with new access keys:"
echo "  aws configure"
echo ""
echo "Option 3: Attach IAM role to EC2 instance (best solution):"
echo "  AWS Console → EC2 → Select instance → Actions → Security → Modify IAM role"
echo ""
