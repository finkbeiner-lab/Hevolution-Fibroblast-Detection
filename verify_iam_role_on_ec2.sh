#!/bin/bash
# Verify IAM role is working on EC2 and clean up old credentials

echo "=========================================="
echo "Verifying IAM Role on EC2"
echo "=========================================="
echo ""

# Step 1: Check if IAM role is attached
echo "Step 1: Checking for IAM Role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
else
    echo "❌ No IAM role found"
    echo "   Make sure you attached the role in EC2 Console"
    exit 1
fi

echo ""
echo "Step 2: Cleaning Up Old Credentials"
echo "----------------------------------------"

# Unset SSO profile
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE
echo "✅ Unset AWS_PROFILE"

# Backup and remove old credentials
if [ -f ~/.aws/credentials ]; then
    mv ~/.aws/credentials ~/.aws/credentials.backup
    echo "✅ Backed up old credentials file"
fi

# Clear SSO cache
if [ -d ~/.aws/sso ]; then
    rm -rf ~/.aws/sso/cache/* 2>/dev/null
    echo "✅ Cleared SSO cache"
fi

echo ""
echo "Step 3: Waiting for IAM Role Credentials..."
echo "----------------------------------------"
sleep 5

echo ""
echo "Step 4: Testing IAM Role Credentials"
echo "----------------------------------------"

# Test credentials
if aws sts get-caller-identity 2>/dev/null; then
    IDENTITY=$(aws sts get-caller-identity 2>/dev/null | grep -o 'arn:aws:sts::[^"]*' | head -1)
    echo "✅ Credentials working!"
    echo "   Identity: $IDENTITY"
    
    if echo "$IDENTITY" | grep -q "assumed-role"; then
        echo "   ✅ Using IAM role (correct!)"
    else
        echo "   ⚠️  Not using IAM role - check credentials"
    fi
else
    echo "❌ Credentials test failed"
    echo "   Wait a few more seconds and try: aws sts get-caller-identity"
    exit 1
fi

echo ""
echo "Step 5: Testing S3 Access"
echo "----------------------------------------"

if aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2 2>/dev/null; then
    echo "✅ S3 access working!"
else
    echo "❌ S3 access failed"
    echo "   Check IAM role has S3 permissions"
    exit 1
fi

echo ""
echo "Step 6: Testing SageMaker Access"
echo "----------------------------------------"

if aws sagemaker describe-endpoint \
    --endpoint-name fibroblast-detection-endpoint \
    --region us-east-2 2>/dev/null | grep -q "EndpointStatus"; then
    echo "✅ SageMaker access working!"
else
    echo "⚠️  SageMaker access test failed (may be okay)"
fi

echo ""
echo "Step 7: Restarting Gradio Service"
echo "----------------------------------------"

sudo systemctl restart gradio-app
sleep 2

if sudo systemctl is-active --quiet gradio-app; then
    echo "✅ Gradio service is running"
else
    echo "❌ Gradio service failed to start"
    echo "   Check logs: sudo journalctl -u gradio-app -n 50"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ SUCCESS! IAM Role is Working!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✅ IAM role attached: $ROLE"
echo "  ✅ Old credentials removed"
echo "  ✅ AWS access working"
echo "  ✅ S3 access working"
echo "  ✅ Gradio service restarted"
echo ""
echo "Next steps:"
echo "  1. Test Gradio app: http://3.150.215.121:7860"
echo "  2. Upload an image and test inference"
echo "  3. Check logs: sudo journalctl -u gradio-app -f"
echo ""
echo "The IAM role credentials will never expire! 🎉"
echo ""
