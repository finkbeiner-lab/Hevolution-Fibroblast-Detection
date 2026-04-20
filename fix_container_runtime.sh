#!/bin/bash
# Fix NVIDIA container runtime configuration

echo "=========================================="
echo "Fixing NVIDIA Container Runtime"
echo "=========================================="
echo ""

# Step 1: Reconfigure the runtime
echo "🔧 Step 1: Reconfiguring NVIDIA container runtime..."
sudo nvidia-ctk runtime configure --runtime=docker

if [ $? -eq 0 ]; then
    echo "✅ Runtime configured successfully"
else
    echo "❌ Failed to configure runtime"
    exit 1
fi

echo ""

# Step 2: Restart Docker
echo "🔄 Step 2: Restarting Docker..."
sudo systemctl restart docker

if [ $? -eq 0 ]; then
    echo "✅ Docker restarted"
else
    echo "❌ Failed to restart Docker"
    exit 1
fi

# Wait a moment for Docker to be ready
sleep 2

echo ""

# Step 3: Verify configuration
echo "🔍 Step 3: Verifying configuration..."
if [ -f /etc/docker/daemon.json ]; then
    echo "✅ daemon.json exists:"
    cat /etc/docker/daemon.json | python3 -m json.tool 2>/dev/null || cat /etc/docker/daemon.json
else
    echo "⚠️  daemon.json not found (this might be okay)"
fi

echo ""

# Step 4: Test GPU access
echo "🧪 Step 4: Testing GPU access..."
echo ""

# First check if nvidia-smi works on host
if nvidia-smi &> /dev/null; then
    echo "✅ nvidia-smi works on host"
    echo "   Testing in Docker..."
    
    if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo "✅ GPU access works in Docker!"
        echo ""
        echo "You can now test your container:"
        echo "  ./test_docker_local.sh"
    else
        echo "❌ GPU access test failed in Docker"
        echo ""
        echo "Trying with explicit runtime..."
        if docker run --rm --runtime=nvidia nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
            echo "✅ Works with --runtime=nvidia flag"
            echo "   Update test_docker_local.sh to use --runtime=nvidia instead of --gpus all"
        else
            echo "❌ Still failing"
            echo ""
            echo "Troubleshooting:"
            echo "  1. Check Docker logs: sudo journalctl -u docker | tail -20"
            echo "  2. Check nvidia-container-cli: nvidia-container-cli info"
            echo "  3. Verify libraries: ldconfig -p | grep libnvidia-ml"
        fi
    fi
else
    echo "⚠️  nvidia-smi doesn't work on host"
    echo "   This needs to be fixed first"
    echo ""
    echo "Check:"
    echo "  1. Driver modules loaded: lsmod | grep nvidia"
    echo "  2. Driver status: sudo dmesg | grep -i nvidia | tail -5"
    echo "  3. You may need to reboot"
fi

echo ""
echo "=========================================="
