#!/bin/bash
# Configure AWS credentials on EC2 (without browser)

echo "=========================================="
echo "AWS Credential Configuration for EC2"
echo "=========================================="
echo ""

# Check if IAM role exists first
echo "Step 1: Checking for IAM Role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
    echo ""
    echo "Testing IAM role credentials..."
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ IAM role is working!"
        echo ""
        echo "You don't need to configure credentials - IAM role handles it!"
        echo "Just make sure ~/.aws/credentials doesn't override it."
        if [ -f ~/.aws/credentials ]; then
            echo ""
            echo "⚠️  Found ~/.aws/credentials - this might override IAM role"
            read -p "Remove it? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                mv ~/.aws/credentials ~/.aws/credentials.backup
                echo "✅ Removed. IAM role will be used now."
            fi
        fi
        exit 0
    fi
else
    echo "❌ No IAM role attached"
    echo ""
fi

echo ""
echo "=========================================="
echo "Option 1: Use Access Keys (Recommended for EC2)"
echo "=========================================="
echo ""
echo "Since EC2 can't open a browser, use Access Keys instead:"
echo ""
echo "1. Go to AWS Console → IAM → Users → Your User → Security Credentials"
echo "2. Create Access Key (if you don't have one)"
echo "3. Copy Access Key ID and Secret Access Key"
echo ""
read -p "Do you have Access Keys ready? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    aws configure
    echo ""
    echo "Testing credentials..."
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ Credentials configured successfully!"
        aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2 && echo "✅ S3 access working!"
    else
        echo "❌ Credentials test failed"
    fi
    exit 0
fi

echo ""
echo "=========================================="
echo "Option 2: Manual SSO Login (From Your Local Machine)"
echo "=========================================="
echo ""
echo "If you must use SSO, do this from YOUR LOCAL MACHINE:"
echo ""
echo "1. On your local machine, run:"
echo "   aws sso login --profile your-profile"
echo ""
echo "2. Copy the credentials from your local machine to EC2:"
echo "   scp ~/.aws/credentials ubuntu@3.150.215.121:~/.aws/"
echo "   scp ~/.aws/config ubuntu@3.150.215.121:~/.aws/"
echo ""
echo "3. But note: SSO credentials expire, so this is temporary!"
echo ""

echo ""
echo "=========================================="
echo "Option 3: Attach IAM Role (BEST SOLUTION)"
echo "=========================================="
echo ""
echo "The best solution is to attach an IAM role to the EC2 instance:"
echo ""
echo "1. AWS Console → EC2 → Select your instance"
echo "2. Actions → Security → Modify IAM role"
echo "3. Create/select role with:"
echo "   - AmazonSageMakerFullAccess"
echo "   - AmazonS3FullAccess"
echo "4. Attach the role"
echo ""
echo "Then on EC2, remove any credentials file:"
echo "   rm ~/.aws/credentials"
echo ""
echo "IAM role credentials never expire and work automatically!"
echo ""
