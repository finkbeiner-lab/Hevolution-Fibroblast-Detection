#!/bin/bash
# Fix NVIDIA driver and container runtime issues

echo "=========================================="
echo "NVIDIA Driver & Container Runtime Fix"
echo "=========================================="
echo ""

# Check if driver is loaded
echo "🔍 Step 1: Checking NVIDIA driver status..."
if lsmod | grep -q nvidia; then
    echo "✅ NVIDIA kernel modules are loaded"
    lsmod | grep nvidia | head -3
else
    echo "❌ NVIDIA kernel modules are NOT loaded"
    echo ""
    echo "The driver is installed but not running. This can happen if:"
    echo "  1. The system needs a reboot"
    echo "  2. Secure Boot is enabled and blocking the driver"
    echo "  3. The driver needs to be reloaded"
    echo ""
    read -p "Try to reload the driver modules? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Attempting to load NVIDIA modules..."
        sudo modprobe nvidia 2>&1 || echo "⚠️  Could not load nvidia module (may need reboot)"
        sudo modprobe nvidia_uvm 2>&1 || echo "⚠️  Could not load nvidia_uvm module"
        sleep 2
        if lsmod | grep -q nvidia; then
            echo "✅ Modules loaded successfully"
        else
            echo "❌ Still cannot load modules. You may need to:"
            echo "  1. Reboot the system"
            echo "  2. Check Secure Boot settings"
            echo "  3. Check dmesg for errors: sudo dmesg | grep -i nvidia"
        fi
    fi
fi

echo ""

# Check nvidia-smi
echo "🔍 Step 2: Testing nvidia-smi..."
if nvidia-smi &> /dev/null; then
    echo "✅ nvidia-smi works!"
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | head -1
else
    echo "❌ nvidia-smi failed"
    echo "   This means the driver is not properly loaded"
    echo "   You may need to reboot your system"
fi

echo ""

# Check container runtime configuration
echo "🔍 Step 3: Checking Docker container runtime configuration..."
if [ -f /etc/docker/daemon.json ]; then
    echo "✅ daemon.json exists"
    cat /etc/docker/daemon.json
else
    echo "⚠️  daemon.json not found"
    echo "   Configuring Docker for NVIDIA runtime..."
    
    # Create daemon.json with nvidia runtime
    sudo mkdir -p /etc/docker
    echo '{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "default-runtime": "nvidia"
}' | sudo tee /etc/docker/daemon.json
    
    echo "✅ Created daemon.json"
    echo "   Restarting Docker..."
    sudo systemctl restart docker
    echo "✅ Docker restarted"
fi

echo ""

# Verify container runtime
echo "🔍 Step 4: Verifying container runtime..."
if docker info 2>/dev/null | grep -q nvidia; then
    echo "✅ NVIDIA runtime is configured in Docker"
    docker info 2>/dev/null | grep -i runtime
else
    echo "⚠️  NVIDIA runtime not found in Docker info"
    echo "   This might be okay if using --gpus flag"
fi

echo ""

# Test GPU access
echo "🧪 Step 5: Testing GPU access in Docker..."
if nvidia-smi &> /dev/null; then
    echo "Testing with Docker..."
    if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo "✅ GPU access works in Docker!"
    else
        echo "❌ GPU access test failed"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Make sure nvidia-smi works: nvidia-smi"
        echo "  2. Check Docker is running: sudo systemctl status docker"
        echo "  3. Try: sudo systemctl restart docker"
        echo "  4. Check logs: sudo journalctl -u docker | tail -20"
    fi
else
    echo "⚠️  Cannot test - nvidia-smi doesn't work"
    echo "   Fix the driver first, then test Docker"
fi

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""
echo "If nvidia-smi doesn't work, you likely need to:"
echo "  1. Reboot your system"
echo "  2. Or check Secure Boot settings"
echo ""
echo "If nvidia-smi works but Docker doesn't, try:"
echo "  sudo systemctl restart docker"
echo "  docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi"
