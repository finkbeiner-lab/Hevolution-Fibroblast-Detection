# Fix Docker Permission Error

## Error Message
```
permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

## Quick Fix (Recommended)

Add your user to the docker group:

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Apply the changes (choose one):
# Option A: Start a new shell session
newgrp docker

# Option B: Log out and log back in
# (Close terminal and reopen, or logout/login)

# Verify it works
docker ps
```

## Alternative Solutions

### Option 1: Use sudo (Not Recommended)
```bash
# Build with sudo
sudo docker build -t fibroblast-detection:latest .

# Push with sudo
sudo docker push YOUR_ECR_URI
```

**Note:** This requires sudo for every Docker command and is not ideal for automation.

### Option 2: Skip Docker Build (If Image Already Exists)
If you already have the Docker image in ECR:

```bash
python sagemaker_deploy.py --skip-ecr --image-uri YOUR_ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
```

### Option 3: Build Manually First
1. Fix Docker permissions (Option 1 above)
2. Build and push manually:
   ```bash
   docker build -t fibroblast-detection:latest .
   aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-2.amazonaws.com
   docker tag fibroblast-detection:latest YOUR_ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
   docker push YOUR_ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
   ```
3. Then run deployment script with `--image-uri` flag

## Verify Fix

After applying the fix, test Docker access:

```bash
# Should work without sudo
docker ps
docker build --help
```

If these commands work, you're good to go! Run the deployment script again:

```bash
python sagemaker_deploy.py
```

## Why This Happens

Docker daemon runs as root, and by default only root can access the Docker socket (`/var/run/docker.sock`). Adding your user to the `docker` group gives you permission to access it without sudo.

## Security Note

Adding a user to the docker group is equivalent to giving that user root access, as Docker can be used to gain root privileges. Only do this on systems you trust.
