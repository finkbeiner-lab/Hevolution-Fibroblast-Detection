#!/bin/bash
# Create instance profile from existing SageMakerFibroblastRole

echo "=========================================="
echo "Create Instance Profile for EC2"
echo "=========================================="
echo ""

ROLE_NAME="SageMakerFibroblastRole"
INSTANCE_PROFILE_NAME="SageMakerFibroblastRole"

echo "Step 1: Checking if instance profile exists..."
if aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" 2>/dev/null; then
    echo "✅ Instance profile already exists: $INSTANCE_PROFILE_NAME"
else
    echo "❌ Instance profile doesn't exist"
    echo ""
    echo "Step 2: Creating instance profile..."
    aws iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME"
    
    if [ $? -eq 0 ]; then
        echo "✅ Instance profile created"
    else
        echo "❌ Failed to create instance profile"
        exit 1
    fi
fi

echo ""
echo "Step 3: Adding role to instance profile..."
# Check if role is already in the profile
ROLES=$(aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" --query 'InstanceProfile.Roles[*].RoleName' --output text 2>/dev/null)

if echo "$ROLES" | grep -q "$ROLE_NAME"; then
    echo "✅ Role already in instance profile"
else
    aws iam add-role-to-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --role-name "$ROLE_NAME"
    
    if [ $? -eq 0 ]; then
        echo "✅ Role added to instance profile"
    else
        echo "❌ Failed to add role to instance profile"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "✅ Instance Profile Ready!"
echo "=========================================="
echo ""
echo "Now go to AWS Console:"
echo "1. EC2 → Instances → Select your instance"
echo "2. Actions → Security → Modify IAM role"
echo "3. You should now see: $INSTANCE_PROFILE_NAME"
echo "4. Select it → Update IAM role"
echo ""
