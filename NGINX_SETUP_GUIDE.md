# Nginx Reverse Proxy Setup for Gradio

Set up nginx to expose Gradio on ports 80/443 while keeping Gradio on port 7860 internally.

## 🚀 Quick Setup

### Step 1: Install and Configure Nginx on EC2

**On your EC2 instance, run:**

```bash
# Install nginx
sudo apt-get update
sudo apt-get install -y nginx

# Create nginx configuration
sudo nano /etc/nginx/sites-available/gradio-app
```

**Paste this configuration:**

```nginx
server {
    listen 80;
    server_name _;

    proxy_read_timeout 600s;
    proxy_connect_timeout 600s;
    proxy_send_timeout 600s;
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

**Save and enable:**

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/gradio-app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

### Step 2: Update Gradio to Bind to Localhost

**Update Gradio service to only listen on localhost:**

```bash
# Edit service file
sudo nano /etc/systemd/system/gradio-app.service
```

**Change this line:**
```
Environment="GRADIO_SERVER_NAME=0.0.0.0"
```

**To:**
```
Environment="GRADIO_SERVER_NAME=127.0.0.1"
```

**Or if using the Gradio-SageMaker.py directly, update it:**
```python
server_name = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")  # Changed from 0.0.0.0
```

**Reload and restart:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart gradio-app
```

### Step 3: Update Security Group

**In AWS Console:**

1. **EC2 Console** → Security Groups → Select your security group
2. **Inbound Rules:**
   - **Remove** port 7860 (if exists)
   - **Add** port 80: Type: HTTP, Source: 0.0.0.0/0
   - **Add** port 443: Type: HTTPS, Source: 0.0.0.0/0 (for SSL later)
3. **Save rules**

### Step 4: Test

```bash
# Test nginx is running
sudo systemctl status nginx

# Test Gradio is running
sudo systemctl status gradio-app

# Test from EC2 itself
curl http://localhost:7860  # Should work
curl http://localhost       # Should also work (via nginx)
```

**From your browser:**
- `http://3.150.215.121` (should work now!)

## 🔒 Optional: Set Up HTTPS (Port 443)

### Install Certbot

```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

### Get SSL Certificate

**If you have a domain:**
```bash
sudo certbot --nginx -d your-domain.com
```

**If you don't have a domain:**
- You can use the EC2 IP, but Let's Encrypt requires a domain
- Or use a self-signed certificate (browser will show warning)

### Self-Signed Certificate (For Testing)

```bash
# Generate self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx-selfsigned.key \
    -out /etc/nginx/ssl/nginx-selfsigned.crt

# Update nginx config to use it
sudo nano /etc/nginx/sites-available/gradio-app
```

Add HTTPS server block (see `nginx_gradio.conf` for example).

## 📋 Or Use the Automated Script

I've created a script that does all of this:

```bash
# Copy to EC2
scp setup_nginx_reverse_proxy.sh ubuntu@3.150.215.121:~/

# On EC2, run it
chmod +x ~/setup_nginx_reverse_proxy.sh
sudo bash ~/setup_nginx_reverse_proxy.sh
```

## ✅ Verification Checklist

- [ ] Nginx installed and running
- [ ] Nginx configuration created at `/etc/nginx/sites-available/gradio-app`
- [ ] Site enabled and default site removed
- [ ] Gradio service updated to bind to `127.0.0.1:7860`
- [ ] Security group allows ports 80 and 443 from 0.0.0.0/0
- [ ] Security group does NOT allow port 7860
- [ ] Can access app via `http://YOUR_EC2_IP`
- [ ] Gradio still works (via nginx proxy)

## 🐛 Troubleshooting

### "502 Bad Gateway"
- Check Gradio is running: `sudo systemctl status gradio-app`
- Check Gradio is on 127.0.0.1:7860: `curl http://127.0.0.1:7860`
- Check nginx logs: `sudo tail -f /var/log/nginx/error.log`

### "Connection refused"
- Check nginx is running: `sudo systemctl status nginx`
- Check nginx config: `sudo nginx -t`
- Check security group allows port 80

### WebSocket not working
- Make sure nginx config has `Upgrade` and `Connection` headers
- Check nginx logs for WebSocket errors

### Timeout errors
- Increase `proxy_read_timeout` in nginx config (already set to 600s)
- Check SageMaker endpoint is responding

## 📊 Architecture

```
Internet (0.0.0.0/0)
    ↓
Security Group (Ports 80, 443 only)
    ↓
EC2 Instance
    ↓
Nginx (Port 80/443) → Reverse Proxy
    ↓
Gradio (127.0.0.1:7860) → Internal only
    ↓
SageMaker Endpoint
```

## 🎯 Summary

**What this does:**
- ✅ Exposes Gradio on standard web ports (80/443)
- ✅ Keeps Gradio internal (127.0.0.1:7860)
- ✅ More secure (no direct access to Gradio port)
- ✅ Ready for SSL/HTTPS
- ✅ Professional setup

**After setup:**
- Access via: `http://YOUR_EC2_IP` (port 80)
- Or: `https://YOUR_EC2_IP` (port 443, after SSL setup)

The app will work exactly the same, but now it's more secure! 🔒
