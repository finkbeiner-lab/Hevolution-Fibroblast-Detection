# Fix: IAM Role Not Showing in EC2 Dropdown

The role `SageMakerFibroblastRole` exists, but it's not showing in the dropdown because it needs to be in an **Instance Profile**.

## 🔧 Solution: Create Instance Profile

### Method 1: AWS Console

1. **Go to IAM Console:**
   - AWS Console → IAM → Roles → `SageMakerFibroblastRole`

2. **Check Trust Policy:**
   - Click on the role
   - Go to "Trust relationships" tab
   - Make sure it includes:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Principal": {
             "Service": "ec2.amazonaws.com"
           },
           "Action": "sts:AssumeRole"
         }
       ]
     }
     ```
   - If not, click "Edit trust policy" and add it

3. **Create Instance Profile:**
   - IAM → Instance profiles → Create instance profile
   - Name: `SageMakerFibroblastRole` (same as role name)
   - Click "Create instance profile"

4. **Add Role to Instance Profile:**
   - Click on the instance profile you just created
   - Click "Add role"
   - Select `SageMakerFibroblastRole`
   - Click "Add role"

5. **Now Attach to EC2:**
   - Go back to EC2 → Instances → Select your instance
   - Actions → Security → Modify IAM role
   - You should now see `SageMakerFibroblastRole` in the dropdown
   - Select it → Update IAM role

### Method 2: AWS CLI (From Your Local Machine)

**Run this from your local machine (with valid AWS credentials):**

```bash
# Step 1: Check if instance profile exists
aws iam get-instance-profile --instance-profile-name SageMakerFibroblastRole

# If it doesn't exist, create it:
aws iam create-instance-profile \
    --instance-profile-name SageMakerFibroblastRole

# Step 2: Add role to instance profile
aws iam add-role-to-instance-profile \
    --instance-profile-name SageMakerFibroblastRole \
    --role-name SageMakerFibroblastRole

# Step 3: Verify it was created
aws iam get-instance-profile --instance-profile-name SageMakerFibroblastRole
```

**Then attach to EC2:**

```bash
# Get your instance ID (from EC2 Console or from instance itself)
INSTANCE_ID="i-xxxxxxxxx"  # Replace with your instance ID

# Attach instance profile
aws ec2 associate-iam-instance-profile \
    --instance-id $INSTANCE_ID \
    --iam-instance-profile Name=SageMakerFibroblastRole \
    --region us-east-2
```

### Method 3: Use the Script

I've created a script that does this automatically:

```bash
# From your local machine (with AWS credentials)
chmod +x create_instance_profile.sh
./create_instance_profile.sh
```

Then go to EC2 Console and the role should appear in the dropdown.

## ✅ Verify Trust Policy

**Important:** The role must trust EC2 service. Check this:

```bash
# From your local machine
aws iam get-role --role-name SageMakerFibroblastRole --query 'Role.AssumeRolePolicyDocument'
```

It should include:
```json
{
  "Principal": {
    "Service": "ec2.amazonaws.com"
  }
}
```

If not, update it:

```bash
# Create trust policy file
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Update trust policy
aws iam update-assume-role-policy \
    --role-name SageMakerFibroblastRole \
    --policy-document file://trust-policy.json
```

## 📋 Complete Checklist

- [ ] Role `SageMakerFibroblastRole` exists
- [ ] Role has trust policy allowing `ec2.amazonaws.com`
- [ ] Instance profile `SageMakerFibroblastRole` exists
- [ ] Role is added to instance profile
- [ ] Instance profile appears in EC2 dropdown
- [ ] Instance profile attached to EC2 instance
- [ ] On EC2: `unset AWS_PROFILE && rm ~/.aws/credentials`
- [ ] On EC2: `aws sts get-caller-identity` shows role ARN
- [ ] Restart Gradio: `sudo systemctl restart gradio-app`

## 🎯 Quick Summary

**The issue:** IAM roles need to be in an "Instance Profile" to attach to EC2.

**The fix:**
1. Create instance profile with same name as role
2. Add role to instance profile
3. Now it will appear in EC2 dropdown
4. Attach it to your instance

After that, the role will work automatically on EC2! 🎉
