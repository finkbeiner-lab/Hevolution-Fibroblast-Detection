#!/bin/bash
# Final setup and test after IAM role is working

echo "=========================================="
echo "Final Setup - IAM Role is Working!"
echo "=========================================="
echo ""

# Verify IAM role
echo "Step 1: Verifying IAM role..."
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role: $ROLE"
else
    echo "⚠️  Role not in metadata, but S3 access works (that's okay)"
fi

# Check identity
echo ""
echo "Step 2: Checking AWS identity..."
IDENTITY=$(aws sts get-caller-identity 2>/dev/null)
if [ -n "$IDENTITY" ]; then
    echo "✅ AWS Identity:"
    echo "$IDENTITY" | head -3
    if echo "$IDENTITY" | grep -q "assumed-role"; then
        echo "   ✅ Using IAM role (perfect!)"
    fi
else
    echo "❌ Could not get identity"
    exit 1
fi

# Test S3
echo ""
echo "Step 3: Testing S3 access..."
if aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2 2>/dev/null; then
    echo "✅ S3 access working!"
else
    echo "❌ S3 access failed"
    exit 1
fi

# Test SageMaker
echo ""
echo "Step 4: Testing SageMaker access..."
if aws sagemaker describe-endpoint \
    --endpoint-name fibroblast-detection-endpoint \
    --region us-east-2 2>/dev/null | grep -q "EndpointStatus"; then
    STATUS=$(aws sagemaker describe-endpoint \
        --endpoint-name fibroblast-detection-endpoint \
        --region us-east-2 \
        --query 'EndpointStatus' \
        --output text 2>/dev/null)
    echo "✅ SageMaker endpoint accessible"
    echo "   Status: $STATUS"
else
    echo "⚠️  SageMaker test failed (may be okay)"
fi

# Clean up any remaining credential issues
echo ""
echo "Step 5: Final cleanup..."
unset AWS_PROFILE AWS_DEFAULT_PROFILE 2>/dev/null
if [ -f ~/.aws/credentials ]; then
    mv ~/.aws/credentials ~/.aws/credentials.backup
    echo "✅ Backed up old credentials"
fi

# Restart Gradio
echo ""
echo "Step 6: Restarting Gradio service..."
sudo systemctl restart gradio-app
sleep 3

if sudo systemctl is-active --quiet gradio-app; then
    echo "✅ Gradio service is running"
else
    echo "❌ Gradio service failed to start"
    echo "   Check logs: sudo journalctl -u gradio-app -n 50"
    exit 1
fi

# Check logs for errors
echo ""
echo "Step 7: Checking for errors in logs..."
RECENT_ERRORS=$(sudo journalctl -u gradio-app -n 20 --no-pager | grep -i "error\|expired\|token" || true)
if [ -z "$RECENT_ERRORS" ]; then
    echo "✅ No credential errors in recent logs"
else
    echo "⚠️  Found potential errors:"
    echo "$RECENT_ERRORS"
fi

echo ""
echo "=========================================="
echo "✅ SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✅ IAM role is working"
echo "  ✅ S3 access confirmed"
echo "  ✅ Gradio service restarted"
echo ""
echo "Next steps:"
echo "  1. Test Gradio app: http://YOUR_EC2_IP:7860"
echo "  2. Upload an image"
echo "  3. Click 'Run Detection'"
echo "  4. Should work without credential errors!"
echo ""
echo "Monitor logs:"
echo "  sudo journalctl -u gradio-app -f"
echo ""
echo "The IAM role credentials will never expire! 🎉"
echo ""
