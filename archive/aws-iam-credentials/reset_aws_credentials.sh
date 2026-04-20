#!/bin/bash
# Reset and reconfigure AWS credentials on EC2

echo "=========================================="
echo "Resetting AWS Credentials"
echo "=========================================="
echo ""

# Backup existing files
echo "Backing up existing credentials..."
mkdir -p ~/.aws/backup
if [ -f ~/.aws/credentials ]; then
    mv ~/.aws/credentials ~/.aws/backup/credentials.$(date +%Y%m%d_%H%M%S)
    echo "✅ Backed up ~/.aws/credentials"
fi

if [ -f ~/.aws/config ]; then
    cp ~/.aws/config ~/.aws/backup/config.$(date +%Y%m%d_%H%M%S)
    echo "✅ Backed up ~/.aws/config"
fi

echo ""
echo "=========================================="
echo "Removed old credentials"
echo "=========================================="
echo ""

# Check if IAM role exists
echo "Checking for IAM role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
    echo ""
    echo "You have an IAM role attached. Testing it..."
    sleep 2
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ IAM role credentials working!"
        echo ""
        echo "Testing S3 access..."
        if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
            echo "✅ S3 access working with IAM role!"
            echo ""
            echo "No need to configure credentials - IAM role is working!"
            echo "Restarting Gradio service..."
            sudo systemctl restart gradio-app
            echo "✅ Done!"
            exit 0
        else
            echo "❌ S3 access failed - check IAM role permissions"
        fi
    else
        echo "❌ IAM role not working - will need to configure credentials"
    fi
else
    echo "❌ No IAM role attached"
    echo ""
fi

echo ""
echo "=========================================="
echo "Configure AWS Credentials"
echo "=========================================="
echo ""
echo "You need to configure AWS credentials."
echo ""
echo "Option 1: Use AWS Access Keys"
echo "  Run: aws configure"
echo "  Enter your Access Key ID, Secret Access Key, Region (us-east-2)"
echo ""
echo "Option 2: Use SSO (if available)"
echo "  export AWS_PROFILE=your-profile"
echo "  aws sso login"
echo ""
echo "After configuring, we'll test the credentials."
echo ""
read -p "Press Enter to continue with 'aws configure' or Ctrl+C to cancel..."

# Run aws configure
aws configure

echo ""
echo "=========================================="
echo "Testing Credentials"
echo "=========================================="
echo ""

# Test credentials
if aws sts get-caller-identity 2>/dev/null; then
    echo "✅ Credentials are valid!"
    echo ""
    echo "Testing S3 access..."
    if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
        echo "✅ S3 access working!"
        echo ""
        echo "Restarting Gradio service..."
        sudo systemctl restart gradio-app
        sleep 2
        echo "✅ Gradio service restarted!"
        echo ""
        echo "Check status:"
        echo "  sudo systemctl status gradio-app"
        echo ""
        echo "View logs:"
        echo "  sudo journalctl -u gradio-app -f"
    else
        echo "❌ S3 access failed"
        echo "   Check IAM permissions for S3 access"
    fi
else
    echo "❌ Credentials test failed"
    echo "   Run 'aws configure' again or check your access keys"
fi

echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="
