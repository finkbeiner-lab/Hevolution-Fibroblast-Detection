#!/bin/bash
# Activate IAM role without rebooting

echo "=========================================="
echo "Activating IAM Role (No Reboot Needed)"
echo "=========================================="
echo ""

# Step 1: Check if role is attached
echo "Step 1: Checking IAM role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role attached: $ROLE"
else
    echo "❌ No IAM role found"
    echo "   Make sure you attached it in EC2 Console"
    exit 1
fi

echo ""
echo "Step 2: Cleaning environment..."
echo "----------------------------------------"

# Unset all AWS environment variables
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN
echo "✅ Cleared AWS environment variables"

# Remove credential files
if [ -f ~/.aws/credentials ]; then
    mv ~/.aws/credentials ~/.aws/credentials.backup
    echo "✅ Backed up credentials file"
fi

# Clear SSO cache
rm -rf ~/.aws/sso/cache/* 2>/dev/null
echo "✅ Cleared SSO cache"

# Clear boto3 cache
rm -rf ~/.cache/boto3/* 2>/dev/null 2>/dev/null || true
rm -rf ~/.cache/aws/* 2>/dev/null 2>/dev/null || true
echo "✅ Cleared AWS cache"

echo ""
echo "Step 3: Waiting for IAM role credentials..."
echo "----------------------------------------"
echo "IAM role credentials are available via instance metadata."
echo "Waiting 5 seconds for them to be ready..."
sleep 5

echo ""
echo "Step 4: Testing IAM role..."
echo "----------------------------------------"

# Force refresh by accessing metadata
curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE > /dev/null
sleep 2

# Test credentials
if aws sts get-caller-identity 2>/dev/null; then
    IDENTITY=$(aws sts get-caller-identity 2>/dev/null)
    echo "✅ IAM role working!"
    echo "   $IDENTITY"
    
    if echo "$IDENTITY" | grep -q "assumed-role"; then
        echo "   ✅ Confirmed: Using IAM role"
    fi
else
    echo "❌ IAM role not working yet"
    echo "   Try waiting 10 more seconds, or reboot the instance"
    exit 1
fi

echo ""
echo "Step 5: Testing S3..."
echo "----------------------------------------"
if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
    echo "✅ S3 access working!"
else
    echo "❌ S3 access failed"
    exit 1
fi

echo ""
echo "Step 6: Restarting Gradio..."
echo "----------------------------------------"
sudo systemctl restart gradio-app
sleep 3

if sudo systemctl is-active --quiet gradio-app; then
    echo "✅ Gradio service running"
else
    echo "❌ Gradio service failed"
    echo "   Check: sudo journalctl -u gradio-app -n 50"
fi

echo ""
echo "=========================================="
echo "✅ Done! No reboot needed."
echo "=========================================="
echo ""
echo "If it's still not working, you can reboot:"
echo "  sudo reboot"
echo ""
echo "But usually it works without rebooting."
echo ""
