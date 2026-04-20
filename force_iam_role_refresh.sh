#!/bin/bash
# Force refresh IAM role credentials on EC2

echo "=========================================="
echo "IAM Role is Attached - Forcing Refresh"
echo "=========================================="
echo ""

echo "The IAM role IS attached to your instance."
echo "Sometimes it takes a moment to be available via metadata service."
echo ""

# Step 1: Clean environment
echo "Step 1: Cleaning environment..."
unset AWS_PROFILE
unset AWS_DEFAULT_PROFILE
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN

if [ -f ~/.aws/credentials ]; then
    mv ~/.aws/credentials ~/.aws/credentials.backup
    echo "✅ Backed up credentials file"
fi

rm -rf ~/.aws/sso/cache/* 2>/dev/null
echo "✅ Environment cleaned"

# Step 2: Try to access role via metadata
echo ""
echo "Step 2: Accessing IAM role via metadata service..."
echo ""

# Try multiple times
for i in {1..5}; do
    echo "Attempt $i/5..."
    ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
    
    if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
        echo "✅ IAM Role found: $ROLE"
        break
    else
        echo "   Not available yet, waiting..."
        sleep 3
    fi
done

# Step 3: If still not available, try rebooting
if [ -z "$ROLE" ] || [ "$ROLE" = "404 - Not Found" ]; then
    echo ""
    echo "⚠️  IAM role not available via metadata service yet"
    echo ""
    echo "This can happen right after attaching. Options:"
    echo ""
    echo "Option 1: Wait 30-60 seconds and try again"
    echo "  curl http://169.254.169.254/latest/meta-data/iam/security-credentials/"
    echo ""
    echo "Option 2: Reboot the instance (recommended)"
    echo "  sudo reboot"
    echo "  (After reboot, IAM role will definitely be available)"
    echo ""
    read -p "Reboot now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Rebooting in 5 seconds... (Ctrl+C to cancel)"
        sleep 5
        sudo reboot
    else
        echo "Waiting 30 seconds and trying again..."
        sleep 30
        ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
        if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
            echo "✅ IAM Role now available: $ROLE"
        else
            echo "❌ Still not available. Please reboot: sudo reboot"
            exit 1
        fi
    fi
fi

# Step 4: Test credentials
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo ""
    echo "Step 3: Testing IAM role credentials..."
    echo "----------------------------------------"
    
    # Force refresh by accessing metadata
    curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE > /dev/null
    sleep 3
    
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ IAM role credentials working!"
        aws sts get-caller-identity
        echo ""
        
        echo "Testing S3 access..."
        if aws s3 ls s3://fibroblast-detection-bucket/ --region us-east-2 2>/dev/null; then
            echo "✅ S3 access working!"
            echo ""
            
            echo "Restarting Gradio..."
            sudo systemctl restart gradio-app
            sleep 2
            
            if sudo systemctl is-active --quiet gradio-app; then
                echo "✅ Gradio service running!"
                echo ""
                echo "=========================================="
                echo "✅ SUCCESS! Everything is working!"
                echo "=========================================="
            else
                echo "⚠️  Gradio service issue - check logs"
            fi
        else
            echo "❌ S3 access failed"
        fi
    else
        echo "❌ Credentials not working yet"
        echo "   Try rebooting: sudo reboot"
    fi
fi

echo ""
