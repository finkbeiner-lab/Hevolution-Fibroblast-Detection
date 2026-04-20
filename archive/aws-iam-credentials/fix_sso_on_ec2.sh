#!/bin/bash
# Fix SSO profile issue on EC2

echo "=========================================="
echo "Fixing SSO Profile on EC2"
echo "=========================================="
echo ""

# Check current profile
echo "Current AWS_PROFILE: ${AWS_PROFILE:-not set}"
echo ""

# Unset SSO profile
echo "Step 1: Removing SSO profile from environment..."
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE
echo "✅ Unset AWS_PROFILE"
echo ""

# Check for IAM role first
echo "Step 2: Checking for IAM Role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
    echo ""
    echo "Removing SSO config to use IAM role..."
    if [ -f ~/.aws/config ]; then
        # Backup config
        cp ~/.aws/config ~/.aws/config.backup
        # Remove or comment out SSO profile
        sed -i '/\[profile admin\]/,/^$/d' ~/.aws/config 2>/dev/null || true
        sed -i '/\[profile admin-session\]/,/^$/d' ~/.aws/config 2>/dev/null || true
        echo "✅ Removed SSO profile from config"
    fi
    if [ -f ~/.aws/credentials ]; then
        mv ~/.aws/credentials ~/.aws/credentials.backup
        echo "✅ Backed up credentials file"
    fi
    echo ""
    echo "Testing IAM role..."
    sleep 2
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ IAM role working!"
        aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 && echo "✅ S3 access working!"
        exit 0
    fi
else
    echo "❌ No IAM role attached"
    echo ""
fi

# Remove SSO config
echo "Step 3: Removing SSO configuration..."
if [ -f ~/.aws/config ]; then
    # Backup
    cp ~/.aws/config ~/.aws/config.backup
    echo "✅ Backed up config"
    
    # Remove SSO profiles
    sed -i '/\[profile admin\]/,/^$/d' ~/.aws/config 2>/dev/null || true
    sed -i '/\[profile admin-session\]/,/^$/d' ~/.aws/config 2>/dev/null || true
    echo "✅ Removed SSO profiles from config"
fi

# Remove SSO credentials cache
if [ -d ~/.aws/sso/cache ]; then
    rm -rf ~/.aws/sso/cache/*
    echo "✅ Cleared SSO cache"
fi

echo ""
echo "=========================================="
echo "Step 4: Configure Access Keys"
echo "=========================================="
echo ""
echo "SSO doesn't work on EC2 (needs browser)."
echo "You need to use Access Keys instead."
echo ""
echo "To get Access Keys:"
echo "1. AWS Console → IAM → Users → Your User → Security Credentials"
echo "2. Create Access Key"
echo "3. Copy Access Key ID and Secret Access Key"
echo ""
read -p "Press Enter to configure with 'aws configure' (or Ctrl+C to cancel)..."

# Configure with access keys
aws configure

echo ""
echo "Testing credentials..."
if aws sts get-caller-identity 2>/dev/null; then
    echo "✅ Credentials working!"
    echo ""
    echo "Testing S3 access..."
    if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
        echo "✅ S3 access working!"
        echo ""
        echo "Restarting Gradio service..."
        sudo systemctl restart gradio-app
        echo "✅ Done!"
    else
        echo "❌ S3 access failed - check IAM permissions"
    fi
else
    echo "❌ Credentials test failed"
    echo "   Run 'aws configure' again"
fi

echo ""
echo "=========================================="
echo "To prevent this in the future:"
echo "=========================================="
echo ""
echo "Add to ~/.bashrc or ~/.profile:"
echo "  unset AWS_PROFILE"
echo "  unset AWS_DEFAULT_PROFILE"
echo ""
echo "Or attach an IAM role to EC2 (best solution)"
echo ""
