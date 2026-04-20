#!/bin/bash
# Check IAM role status and troubleshoot

echo "=========================================="
echo "Checking IAM Role Status"
echo "=========================================="
echo ""

echo "Step 1: Checking instance metadata..."
echo "----------------------------------------"

# Check instance ID
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
if [ -n "$INSTANCE_ID" ]; then
    echo "✅ Instance ID: $INSTANCE_ID"
else
    echo "❌ Could not get instance ID"
    echo "   Instance metadata service not accessible"
    exit 1
fi

# Check IAM role
ROLE=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -n "$ROLE" ] && [ "$ROLE" != "404 - Not Found" ]; then
    echo "✅ IAM Role found: $ROLE"
    echo ""
    echo "Testing role credentials..."
    sleep 2
    if aws sts get-caller-identity 2>/dev/null; then
        echo "✅ IAM role is working!"
        aws sts get-caller-identity
    else
        echo "⚠️  Role found but credentials not working yet"
        echo "   Wait 10-20 seconds and try again"
    fi
else
    echo "❌ No IAM role attached to this instance"
    echo ""
    echo "=========================================="
    echo "Troubleshooting Steps"
    echo "=========================================="
    echo ""
    echo "The IAM role is not attached. Do this:"
    echo ""
    echo "1. Go to AWS Console → EC2 → Instances"
    echo "2. Find instance ID: $INSTANCE_ID"
    echo "3. Select it → Actions → Security → Modify IAM role"
    echo "4. Select 'SageMakerFibroblastRole' from dropdown"
    echo "5. Click 'Update IAM role'"
    echo "6. Wait 10-20 seconds"
    echo "7. Run this script again"
    echo ""
    echo "If the role doesn't appear in dropdown:"
    echo "  - Make sure instance profile exists"
    echo "  - Check trust policy includes ec2.amazonaws.com"
    echo ""
    echo "To check from AWS CLI (from your local machine):"
    echo "  aws ec2 describe-instances \\"
    echo "      --instance-ids $INSTANCE_ID \\"
    echo "      --query 'Reservations[0].Instances[0].IamInstanceProfile' \\"
    echo "      --region us-east-2"
    echo ""
fi

echo ""
echo "Step 2: Current AWS Identity"
echo "----------------------------------------"
if aws sts get-caller-identity 2>/dev/null; then
    echo "Current identity:"
    aws sts get-caller-identity
else
    echo "❌ No AWS credentials working"
    echo "   Need to attach IAM role or configure credentials"
fi

echo ""
echo "Step 3: Environment Variables"
echo "----------------------------------------"
if [ -n "$AWS_PROFILE" ]; then
    echo "⚠️  AWS_PROFILE is set: $AWS_PROFILE"
    echo "   This might override IAM role"
    echo "   Run: unset AWS_PROFILE"
else
    echo "✅ AWS_PROFILE not set"
fi

echo ""
