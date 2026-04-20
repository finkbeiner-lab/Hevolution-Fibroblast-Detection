#!/bin/bash

echo "=========================================="
echo "Reverting Gradio to listen on 0.0.0.0"
echo "=========================================="
echo ""

# Stop the service
echo "1. Stopping gradio-app service..."
sudo systemctl stop gradio-app

# Change from 127.0.0.1 to 0.0.0.0
echo "2. Changing GRADIO_SERVER_NAME from 127.0.0.1 to 0.0.0.0..."
sudo sed -i 's/GRADIO_SERVER_NAME=127.0.0.1/GRADIO_SERVER_NAME=0.0.0.0/' /etc/systemd/system/gradio-app.service

# Reload systemd
echo "3. Reloading systemd daemon..."
sudo systemctl daemon-reload

# Start the service
echo "4. Starting gradio-app service..."
sudo systemctl start gradio-app

# Wait a moment
sleep 2

# Check status
echo "5. Checking service status..."
sudo systemctl status gradio-app --no-pager -l | head -15

echo ""
echo "=========================================="
echo "Verification"
echo "=========================================="

# Check if port is listening on 0.0.0.0
if sudo ss -tlnp | grep -q "0.0.0.0:7860"; then
    echo "✓ Gradio is now listening on 0.0.0.0:7860"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR_EC2_IP")
    echo ""
    echo "You can access it at: http://${PUBLIC_IP}:7860"
    echo "(Make sure your security group allows port 7860)"
else
    echo "✗ Gradio is not listening on 0.0.0.0:7860"
    echo "Check the service logs: sudo journalctl -u gradio-app -n 20"
fi
echo ""
