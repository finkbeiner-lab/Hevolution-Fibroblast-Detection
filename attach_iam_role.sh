#!/bin/bash
# Script to help attach IAM role to EC2 and verify it works

echo "=========================================="
echo "Attach SageMakerFibroblastRole to EC2"
echo "=========================================="
echo ""

echo "STEP 1: Attach IAM Role via AWS Console"
echo "----------------------------------------"
echo "1. Go to: AWS Console → EC2 → Instances"
echo "2. Select your instance (IP: 3.150.215.121)"
echo "3. Actions → Security → Modify IAM role"
echo "4. Select: SageMakerFibroblastRole"
echo "5. Click: Update IAM role"
echo ""
read -p "Press Enter after you've attached the role in AWS Console..."

echo ""
echo "STEP 2: Verifying IAM Role is Attached"
echo "----------------------------------------"
echo ""

# Check if role is attached
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
    echo ""
    
    # Wait a moment for credentials to be available
    echo "Waiting for IAM role credentials to be available..."
    sleep 5
    
    # Clean up old credentials
    echo ""
    echo "STEP 3: Cleaning Up Old Credentials"
    echo "----------------------------------------"
    unset AWS_PROFILE
    unset AWS_DEFAULT_PROFILE
    echo "✅ Unset AWS_PROFILE"
    
    if [ -f ~/.aws/credentials ]; then
        mv ~/.aws/credentials ~/.aws/credentials.backup
        echo "✅ Backed up old credentials file"
    fi
    
    rm -rf ~/.aws/sso/cache/* 2>/dev/null
    echo "✅ Cleared SSO cache"
    
    echo ""
    echo "STEP 4: Testing IAM Role Credentials"
    echo "----------------------------------------"
    
    # Test credentials
    if aws sts get-caller-identity 2>/dev/null; then
        IDENTITY=$(aws sts get-caller-identity 2>/dev/null)
        echo "✅ Credentials working!"
        echo "   Identity: $IDENTITY"
        echo ""
        
        echo "Testing S3 access..."
        if aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2 2>/dev/null; then
            echo "✅ S3 access working!"
            echo ""
            
            echo "STEP 5: Restarting Gradio Service"
            echo "----------------------------------------"
            sudo systemctl restart gradio-app
            sleep 2
            echo "✅ Gradio service restarted!"
            echo ""
            
            echo "=========================================="
            echo "✅ SUCCESS! IAM Role is working!"
            echo "=========================================="
            echo ""
            echo "Check service status:"
            echo "  sudo systemctl status gradio-app"
            echo ""
            echo "View logs:"
            echo "  sudo journalctl -u gradio-app -f"
            echo ""
        else
            echo "❌ S3 access failed"
            echo "   Check IAM role has S3 permissions"
        fi
    else
        echo "❌ Credentials test failed"
        echo "   Wait a few more seconds and try:"
        echo "   aws sts get-caller-identity"
    fi
else
    echo "❌ IAM Role not found"
    echo ""
    echo "Make sure you:"
    echo "1. Attached the role in AWS Console"
    echo "2. Waited 10-20 seconds for it to take effect"
    echo "3. Run this script again"
fi

echo ""
