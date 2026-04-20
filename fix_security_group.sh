#!/bin/bash

echo "=========================================="
echo "EC2 Security Group Configuration Helper"
echo "=========================================="
echo ""

# Check if AWS CLI is available
if ! command -v aws >/dev/null 2>&1; then
    echo "✗ AWS CLI is not installed or not in PATH"
    echo "  Install it with: sudo apt-get install awscli"
    exit 1
fi

# Get instance ID
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
if [ -z "$INSTANCE_ID" ]; then
    echo "✗ Could not determine instance ID"
    echo "  Are you running this on an EC2 instance?"
    exit 1
fi

echo "Instance ID: $INSTANCE_ID"
echo ""

# Get security group ID
echo "Getting security group information..."
SG_INFO=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].SecurityGroups[*].[GroupId,GroupName]' --output text 2>/dev/null)

if [ -z "$SG_INFO" ]; then
    echo "✗ Could not retrieve security group information"
    echo "  Check your AWS credentials: aws configure list"
    exit 1
fi

SG_ID=$(echo "$SG_INFO" | head -1 | awk '{print $1}')
SG_NAME=$(echo "$SG_INFO" | head -1 | awk '{print $2}')

echo "Security Group ID: $SG_ID"
echo "Security Group Name: $SG_NAME"
echo ""

# Check current rules for port 7860
echo "Checking current rules for port 7860..."
CURRENT_RULES=$(aws ec2 describe-security-groups --group-ids "$SG_ID" --query 'SecurityGroups[0].IpPermissions[?FromPort==`7860`]' --output json 2>/dev/null)

if [ "$CURRENT_RULES" != "[]" ] && [ -n "$CURRENT_RULES" ]; then
    echo "✓ Port 7860 rules found:"
    echo "$CURRENT_RULES" | python3 -m json.tool 2>/dev/null || echo "$CURRENT_RULES"
else
    echo "✗ No rules found for port 7860"
fi
echo ""

# Get your current public IP
MY_IP=$(curl -s https://checkip.amazonaws.com)
echo "Your current public IP: $MY_IP"
echo ""

echo "=========================================="
echo "To allow access from your IP, run:"
echo "=========================================="
echo ""
echo "aws ec2 authorize-security-group-ingress \\"
echo "  --group-id $SG_ID \\"
echo "  --protocol tcp \\"
echo "  --port 7860 \\"
echo "  --cidr ${MY_IP}/32"
echo ""
echo "Or to allow from anywhere (less secure, for testing only):"
echo ""
echo "aws ec2 authorize-security-group-ingress \\"
echo "  --group-id $SG_ID \\"
echo "  --protocol tcp \\"
echo "  --port 7860 \\"
echo "  --cidr 0.0.0.0/0"
echo ""
echo "=========================================="
read -p "Do you want to add a rule to allow port 7860 from your IP ($MY_IP)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Adding rule..."
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 7860 \
        --cidr "${MY_IP}/32" 2>&1
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ Rule added successfully!"
        echo ""
        PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
        echo "You should now be able to access:"
        echo "  http://${PUBLIC_IP}:7860"
    else
        echo ""
        echo "✗ Failed to add rule. The rule might already exist."
        echo "  Check the error message above."
    fi
fi
echo ""
