#!/bin/bash

echo "=========================================="
echo "Troubleshooting External Access to Gradio"
echo "=========================================="
echo ""

# Get EC2 instance metadata
echo "1. Checking EC2 instance information..."
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null)
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)

echo "   Public IP: ${PUBLIC_IP:-Not available}"
echo "   Private IP: ${PRIVATE_IP:-Not available}"
echo "   Instance ID: ${INSTANCE_ID:-Not available}"
echo ""

# Check if Gradio is listening on 0.0.0.0
echo "2. Checking if Gradio is listening on all interfaces..."
if sudo ss -tlnp | grep -q ":7860"; then
    LISTEN_INFO=$(sudo ss -tlnp | grep ":7860")
    echo "   ✓ Port 7860 is listening:"
    echo "     $LISTEN_INFO"
    if echo "$LISTEN_INFO" | grep -q "0.0.0.0:7860"; then
        echo "   ✓ Listening on 0.0.0.0 (all interfaces) - Good!"
    else
        echo "   ✗ NOT listening on 0.0.0.0 - This is the problem!"
    fi
else
    echo "   ✗ Port 7860 is NOT listening"
fi
echo ""

# Check local connection
echo "3. Testing local connection..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:7860 | grep -q "200\|302\|307"; then
    echo "   ✓ Local connection works"
else
    echo "   ✗ Local connection failed"
fi
echo ""

# Check if firewall (ufw) is blocking
echo "4. Checking local firewall (ufw)..."
if command -v ufw >/dev/null 2>&1; then
    UFW_STATUS=$(sudo ufw status 2>/dev/null | head -1)
    echo "   $UFW_STATUS"
    if echo "$UFW_STATUS" | grep -q "Status: active"; then
        echo "   ⚠️  UFW is active - checking port 7860..."
        if sudo ufw status | grep -q "7860"; then
            echo "   Port 7860 rules:"
            sudo ufw status | grep 7860
        else
            echo "   ✗ Port 7860 is NOT allowed in UFW"
            echo "   Run: sudo ufw allow 7860/tcp"
        fi
    else
        echo "   ✓ UFW is inactive (not blocking)"
    fi
else
    echo "   ✓ UFW not installed (not blocking)"
fi
echo ""

# Test from inside EC2 using public IP
echo "5. Testing connection using public IP from inside EC2..."
if [ -n "$PUBLIC_IP" ]; then
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://${PUBLIC_IP}:7860 2>&1)
    if echo "$RESPONSE" | grep -q "200\|302\|307"; then
        echo "   ✓ Connection to ${PUBLIC_IP}:7860 works from inside EC2"
    else
        echo "   ✗ Connection to ${PUBLIC_IP}:7860 failed from inside EC2"
        echo "   Response: $RESPONSE"
        echo "   This suggests a security group issue"
    fi
else
    echo "   ⚠️  Could not determine public IP"
fi
echo ""

echo "=========================================="
echo "Most Likely Issue: EC2 Security Group"
echo "=========================================="
echo ""
echo "Your EC2 security group probably doesn't allow inbound traffic on port 7860."
echo ""
echo "To fix this:"
echo "1. Go to AWS Console → EC2 → Security Groups"
echo "2. Find the security group attached to your instance"
echo "3. Click 'Edit inbound rules'"
echo "4. Add a new rule:"
echo "   - Type: Custom TCP"
echo "   - Port: 7860"
echo "   - Source: Your IP address (or 0.0.0.0/0 for testing)"
echo "5. Save rules"
echo ""
echo "Or use AWS CLI:"
echo "  aws ec2 authorize-security-group-ingress \\"
echo "    --group-id YOUR_SECURITY_GROUP_ID \\"
echo "    --protocol tcp \\"
echo "    --port 7860 \\"
echo "    --cidr 0.0.0.0/0"
echo ""
echo "After updating the security group, test again:"
echo "  http://${PUBLIC_IP:-YOUR_EC2_IP}:7860"
echo ""
