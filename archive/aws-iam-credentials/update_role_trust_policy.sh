#!/bin/bash
# Update SageMakerFibroblastRole trust policy to include EC2

echo "=========================================="
echo "Update IAM Role Trust Policy"
echo "=========================================="
echo ""

ROLE_NAME="SageMakerFibroblastRole"
TRUST_POLICY_FILE="update_trust_policy.json"

echo "Current trust policy only allows SageMaker."
echo "Updating to also allow EC2..."
echo ""

# Check if policy file exists
if [ ! -f "$TRUST_POLICY_FILE" ]; then
    echo "Creating trust policy file..."
    cat > "$TRUST_POLICY_FILE" << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": [
                    "sagemaker.amazonaws.com",
                    "ec2.amazonaws.com"
                ]
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF
    echo "✅ Created $TRUST_POLICY_FILE"
fi

echo "Updating trust policy for role: $ROLE_NAME"
echo ""

aws iam update-assume-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-document file://"$TRUST_POLICY_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Trust policy updated successfully!"
    echo ""
    echo "The role now trusts both:"
    echo "  - sagemaker.amazonaws.com (for SageMaker)"
    echo "  - ec2.amazonaws.com (for EC2)"
    echo ""
    echo "Next steps:"
    echo "1. Create instance profile (if not exists):"
    echo "   aws iam create-instance-profile --instance-profile-name SageMakerFibroblastRole"
    echo ""
    echo "2. Add role to instance profile:"
    echo "   aws iam add-role-to-instance-profile \\"
    echo "       --instance-profile-name SageMakerFibroblastRole \\"
    echo "       --role-name SageMakerFibroblastRole"
    echo ""
    echo "3. Then attach to EC2 via Console or CLI"
else
    echo ""
    echo "❌ Failed to update trust policy"
    echo "   Check your AWS credentials and permissions"
    exit 1
fi
