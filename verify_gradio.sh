#!/bin/bash

echo "=========================================="
echo "Gradio Service Verification"
echo "=========================================="
echo ""

# Check if service exists
echo "1. Checking if gradio-app service exists..."
if systemctl list-unit-files | grep -q gradio-app; then
    echo "   ✓ Service found"
else
    echo "   ✗ Service not found"
    exit 1
fi
echo ""

# Check service status
echo "2. Checking service status..."
sudo systemctl status gradio-app --no-pager -l
echo ""

# Check if service is active
if systemctl is-active --quiet gradio-app; then
    echo "   ✓ Service is ACTIVE"
else
    echo "   ✗ Service is NOT active"
    echo ""
    echo "   Checking recent logs..."
    sudo journalctl -u gradio-app -n 20 --no-pager
    exit 1
fi
echo ""

# Check if port 7860 is listening
echo "3. Checking if port 7860 is listening..."
if sudo netstat -tlnp | grep -q :7860 || sudo ss -tlnp | grep -q :7860; then
    echo "   ✓ Port 7860 is listening"
    sudo netstat -tlnp | grep :7860 || sudo ss -tlnp | grep :7860
else
    echo "   ✗ Port 7860 is NOT listening"
fi
echo ""

# Test localhost connection
echo "4. Testing localhost:7860 connection..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:7860 | grep -q "200\|302\|307"; then
    echo "   ✓ Gradio is responding on localhost:7860"
    echo "   Response code: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:7860)"
else
    echo "   ✗ Gradio is NOT responding"
    echo "   Response code: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:7860)"
fi
echo ""

# Check recent logs for errors
echo "5. Recent service logs (last 10 lines)..."
sudo journalctl -u gradio-app -n 10 --no-pager
echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
if systemctl is-active --quiet gradio-app && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860 | grep -q "200\|302\|307"; then
    echo "✓ Gradio is working! You can proceed with nginx setup."
    echo ""
    echo "To access Gradio directly:"
    echo "  - From EC2: curl http://localhost:7860"
    echo "  - From local machine (if security group allows): http://YOUR_EC2_IP:7860"
else
    echo "✗ Gradio is not working properly. Check the logs above."
    echo ""
    echo "Common issues:"
    echo "  - Check AWS credentials: aws configure list"
    echo "  - Check environment variables in service file"
    echo "  - Verify Gradio-SageMaker.py exists at: /home/ubuntu/fibroblast-app/Gradio-SageMaker.py"
    echo "  - Check if virtual environment has required packages"
fi
echo ""
