# Fix GPU Access in Docker

If you see errors like:
```
nvidia-container-cli: initialization error: load library failed: libnvidia-ml.so.1: cannot
WARNING: The NVIDIA Driver was not detected. GPU functionality will not be available.
```

This means Docker cannot access your GPU. Follow these steps to fix it.

## Quick Fix: Install NVIDIA Container Toolkit

### Step 1: Install NVIDIA Container Toolkit

```bash
# Add NVIDIA's GPG key and repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Update package list
sudo apt-get update

# Install NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit

# Restart Docker daemon
sudo systemctl restart docker
```

### Step 2: Verify Installation

```bash
# Test GPU access in Docker
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

If this works, you should see your GPU information. If not, continue to troubleshooting.

### Step 3: Test Your Container

```bash
# Now test your container with GPU
./test_docker_local.sh
```

---

## Alternative: Manual Installation

If the above doesn't work, try the official installation method:

### Ubuntu/Debian

```bash
# Remove old versions
sudo apt-get remove -y nvidia-docker2 docker-ce-cli

# Add NVIDIA's repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## Verify GPU Access

After installation, verify:

```bash
# 1. Check nvidia-smi works
nvidia-smi

# 2. Check Docker can see GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# 3. Check container runtime
docker info | grep -i runtime
```

You should see `nvidia` in the runtime list.

---

## Troubleshooting

### Issue: "libnvidia-ml.so.1: cannot open shared object file"

**Symptoms:**
- Error: `nvidia-container-cli: initialization error: load library failed: libnvidia-ml.so.1: cannot open shared object file`
- Libraries exist but container can't find them
- `nvidia-smi` may or may not work on host

**Solution:**
1. **Reconfigure container runtime:**
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

2. **Verify library paths:**
   ```bash
   # Check libraries are accessible
   ldconfig -p | grep libnvidia-ml
   # Should show: /lib/x86_64-linux-gnu/libnvidia-ml.so.1
   ```

3. **If nvidia-smi doesn't work on host:**
   - Check if modules are loaded: `lsmod | grep nvidia`
   - If modules are loaded but nvidia-smi fails, you may need to reboot
   - Or check for driver issues: `sudo dmesg | grep -i nvidia | tail -10`

4. **Test with verbose output:**
   ```bash
   docker run --rm --gpus all --runtime=nvidia nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
   ```

### Issue: "nvidia-container-cli: initialization error"

**Solution:**
1. Make sure NVIDIA drivers are installed: `nvidia-smi` should work
2. Reinstall NVIDIA Container Toolkit (see above)
3. Restart Docker: `sudo systemctl restart docker`
4. Reconfigure runtime: `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`

### Issue: "Cannot connect to Docker daemon"

**Solution:**
```bash
# Add user to docker group (if not already)
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

### Issue: GPU still not detected in container

**Solution:**
1. Verify driver: `nvidia-smi`
2. Check Docker runtime: `docker info | grep -i runtime`
3. Test with simple container: `docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi`
4. Check container logs: `docker logs <container-name>`

### Issue: Permission denied

**Solution:**
```bash
# Fix Docker permissions
sudo usermod -aG docker $USER
newgrp docker
```

---

## Test Without GPU (Fallback)

If you can't get GPU working, the container will fall back to CPU:

```bash
# The test script will automatically detect and use CPU if GPU is unavailable
./test_docker_local.sh
```

Note: CPU inference will be much slower, but it will work for testing.

---

## References

- [NVIDIA Container Toolkit Installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [Docker GPU Support](https://docs.docker.com/config/containers/resource_constraints/#gpu)
