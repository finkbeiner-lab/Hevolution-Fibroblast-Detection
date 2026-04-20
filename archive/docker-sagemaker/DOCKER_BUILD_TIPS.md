# Docker Build Memory Error Fix

## Error: Exit Code 137
Exit code 137 means the process was killed due to **out of memory** during Docker build.

## Solutions

### Option 1: Increase Docker Memory Limit

**Docker Desktop:**
1. Open Docker Desktop → Settings → Resources
2. Increase Memory to at least **8GB** (recommended: 12GB+)
3. Apply & Restart

**Linux:**
```bash
# Check current memory limit
docker system info | grep -i memory

# If using Docker with systemd, increase memory limit in systemd config
```

### Option 2: Build with More Memory Available

```bash
# Free up system memory before building
# Close other applications
# Then build:
docker build -t fibroblast-detection:latest .
```

### Option 3: Build on a Machine with More RAM

- Use a cloud instance (EC2) with more memory
- Or build on a machine with 16GB+ RAM

### Option 4: Use Multi-Stage Build (Advanced)

The Dockerfile has been optimized to:
- Install PyTorch separately (without torchaudio)
- Use `--no-cache-dir` to reduce memory
- Install packages in smaller steps

### Option 5: Build Without GPU Support First (Test)

If you just want to test the build process:

```dockerfile
# Temporarily comment out PyTorch CUDA installation
# RUN pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

Then install PyTorch CPU version:
```bash
RUN pip3 install --no-cache-dir torch torchvision
```

**Note:** This won't work for Cellpose GPU, but helps test the build process.

## Recommended Approach

1. **Increase Docker memory to 12GB+** (easiest)
2. **Close other applications** to free RAM
3. **Build during low system usage**
4. If still fails, build on a cloud instance with more RAM

## Verify Memory

```bash
# Check available memory
free -h

# Check Docker memory limit
docker system info | grep -i memory
```

## Alternative: Build on EC2

If local build keeps failing:

1. Launch EC2 instance (t3.large or larger, 8GB+ RAM)
2. Install Docker
3. Clone repo and build there
4. Push to ECR from EC2
