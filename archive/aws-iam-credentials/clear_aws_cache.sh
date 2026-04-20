#!/bin/bash
# Remove AWS credentials and cache

echo "=========================================="
echo "Clearing AWS Credentials & Cache"
echo "=========================================="
echo ""

# Unset environment variables
echo "Unsetting AWS environment variables..."
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN
unset AWS_SECURITY_TOKEN
echo "✅ Environment variables cleared"
echo ""

# Backup and remove credentials file
if [ -f ~/.aws/credentials ]; then
    cp ~/.aws/credentials ~/.aws/credentials.backup.$(date +%Y%m%d_%H%M%S)
    rm ~/.aws/credentials
    echo "✅ Removed ~/.aws/credentials (backup created)"
else
    echo "ℹ️  No ~/.aws/credentials file"
fi
echo ""

# Clear SSO cache
if [ -d ~/.aws/sso/cache ]; then
    rm -rf ~/.aws/sso/cache/*
    echo "✅ Cleared ~/.aws/sso/cache/"
else
    echo "ℹ️  No SSO cache directory"
fi
echo ""

# Clear boto3 cache (if exists)
if [ -d ~/.cache/boto3 ]; then
    rm -rf ~/.cache/boto3/*
    echo "✅ Cleared ~/.cache/boto3/"
fi
if [ -d ~/.cache/aws ]; then
    rm -rf ~/.cache/aws/*
    echo "✅ Cleared ~/.cache/aws/"
fi
echo ""

# Optional: remove config (comment out if you want to keep config)
# if [ -f ~/.aws/config ]; then
#     cp ~/.aws/config ~/.aws/config.backup
#     rm ~/.aws/config
#     echo "✅ Removed ~/.aws/config"
# fi

echo "=========================================="
echo "✅ AWS cache cleared!"
echo "=========================================="
echo ""
echo "Next: Run 'aws sso login --profile admin' to log in again"
echo "Or: Run 'aws configure' to set up credentials"
echo ""
