#!/bin/bash
# Setup nginx reverse proxy for Gradio on EC2

echo "=========================================="
echo "Setting up Nginx Reverse Proxy"
echo "=========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "This script needs sudo privileges"
    echo "Run: sudo bash $0"
    exit 1
fi

echo "Step 1: Installing nginx..."
apt-get update
apt-get install -y nginx

echo ""
echo "Step 2: Creating nginx configuration..."
cat > /etc/nginx/sites-available/gradio-app << 'EOF'
server {
    listen 80;
    server_name _;  # Accept any hostname (or use your domain)

    # Increase timeouts for long-running requests
    proxy_read_timeout 600s;
    proxy_connect_timeout 600s;
    proxy_send_timeout 600s;

    # Increase body size for image uploads
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        
        # WebSocket support (Gradio uses WebSockets)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Buffering
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF

echo "✅ Created nginx configuration"

echo ""
echo "Step 3: Enabling site..."
ln -sf /etc/nginx/sites-available/gradio-app /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Remove default site
echo "✅ Enabled gradio-app site"

echo ""
echo "Step 4: Testing nginx configuration..."
nginx -t
if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration has errors"
    exit 1
fi

echo ""
echo "Step 5: Starting nginx..."
systemctl enable nginx
systemctl restart nginx

if systemctl is-active --quiet nginx; then
    echo "✅ Nginx is running"
else
    echo "❌ Nginx failed to start"
    systemctl status nginx
    exit 1
fi

echo ""
echo "Step 6: Updating Gradio to bind to localhost..."
# Update Gradio service to bind to 127.0.0.1 instead of 0.0.0.0
if [ -f /etc/systemd/system/gradio-app.service ]; then
    sed -i 's/GRADIO_SERVER_NAME=0.0.0.0/GRADIO_SERVER_NAME=127.0.0.1/' /etc/systemd/system/gradio-app.service
    systemctl daemon-reload
    systemctl restart gradio-app
    echo "✅ Updated Gradio to bind to localhost"
else
    echo "⚠️  Gradio service file not found at /etc/systemd/system/gradio-app.service"
    echo "   Make sure GRADIO_SERVER_NAME=127.0.0.1 in your service file"
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Nginx is now configured as a reverse proxy:"
echo "  - External: http://YOUR_EC2_IP (port 80)"
echo "  - Internal: Gradio on 127.0.0.1:7860"
echo ""
echo "Next steps:"
echo "  1. Update security group to only allow ports 80 and 443"
echo "  2. Remove port 7860 from security group"
echo "  3. Test: http://YOUR_EC2_IP"
echo ""
echo "For HTTPS (port 443), set up SSL certificate:"
echo "  sudo certbot --nginx -d your-domain.com"
echo ""
