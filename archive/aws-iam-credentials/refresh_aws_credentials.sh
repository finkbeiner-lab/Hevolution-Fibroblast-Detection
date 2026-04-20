#!/bin/bash
# Script to refresh AWS SSO credentials

echo "=========================================="
echo "AWS Credential Refresh Helper"
echo "=========================================="
echo ""

# Check current credentials
echo "Checking current AWS identity..."
if aws sts get-caller-identity &>/dev/null; then
    echo "✅ Credentials are valid"
    aws sts get-caller-identity
    exit 0
else
    echo "❌ Credentials expired or invalid"
    echo ""
fi

# Show available profiles
echo "Available AWS SSO profiles:"
grep -E "^\[profile" ~/.aws/config 2>/dev/null | sed 's/\[profile //;s/\]//' || echo "No profiles found"
echo ""

# Try to refresh with admin profile
echo "Attempting to refresh credentials with 'admin' profile..."
export AWS_PROFILE=admin

# For AWS CLI v2, use: aws sso login --profile admin
# For AWS CLI v1, try alternative methods
if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version 2>&1 | grep -oP 'aws-cli/\K[0-9]+' | head -1)
    if [ "$AWS_VERSION" -ge 2 ]; then
        echo "Using AWS CLI v2..."
        aws sso login --profile admin
    else
        echo "Using AWS CLI v1..."
        echo ""
        echo "⚠️  AWS CLI v1 has limited SSO support."
        echo ""
        echo "Please try one of these options:"
        echo ""
        echo "Option 1: Upgrade to AWS CLI v2 (Recommended)"
        echo "  curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"awscliv2.zip\""
        echo "  unzip awscliv2.zip"
        echo "  sudo ./aws/install"
        echo "  aws sso login --profile admin"
        echo ""
        echo "Option 2: Use AWS SSO Portal (Manual)"
        echo "  1. Open: https://nu-sso.awsapps.com/start"
        echo "  2. Login and select your role"
        echo "  3. Copy temporary credentials to ~/.aws/credentials"
        echo ""
        echo "Option 3: Try SSO login with browser"
        echo "  aws configure sso --profile admin"
        echo ""
        exit 1
    fi
fi

# Verify after login
echo ""
echo "Verifying credentials..."
if aws sts get-caller-identity &>/dev/null; then
    echo "✅ Credentials refreshed successfully!"
    aws sts get-caller-identity
else
    echo "❌ Still unable to authenticate"
    echo "Please follow the manual steps above"
    exit 1
fi
