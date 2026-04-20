#!/bin/bash
# Script to install NVIDIA Container Toolkit for Docker GPU support

set -e

echo "=========================================="
echo "NVIDIA Container Toolkit Installation"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "⚠️  Please run this script without sudo"
    echo "   It will prompt for sudo when needed"
    exit 1
fi

# Check if nvidia-smi works
echo "🔍 Step 1: Checking NVIDIA driver..."
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ nvidia-smi not found. Please install NVIDIA drivers first."
    exit 1
fi

if ! nvidia-smi &> /dev/null; then
    echo "❌ nvidia-smi failed. Please check your NVIDIA driver installation."
    exit 1
fi

echo "✅ NVIDIA driver detected"
nvidia-smi --query-gpu=name --format=csv,noheader | head -1
echo ""

# Check if already installed
echo "🔍 Step 2: Checking if NVIDIA Container Toolkit is already installed..."
if dpkg -l | grep -q nvidia-container-toolkit; then
    echo "✅ NVIDIA Container Toolkit is already installed"
    echo ""
    echo "If you're still having issues, try:"
    echo "  sudo systemctl restart docker"
    echo "  docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi"
    exit 0
fi

# Detect distribution
echo "🔍 Step 3: Detecting Linux distribution..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRIBUTION=$ID$VERSION_ID
    echo "   Detected: $DISTRIBUTION"
else
    echo "❌ Cannot detect distribution. Please install manually."
    exit 1
fi

# Install NVIDIA Container Toolkit
echo ""
echo "📦 Step 4: Installing NVIDIA Container Toolkit..."
echo "   This will require sudo privileges"
echo ""

# Add GPG key
echo "   Adding NVIDIA GPG key..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# Add repository
echo "   Adding NVIDIA repository..."
curl -s -L https://nvidia.github.io/libnvidia-container/$DISTRIBUTION/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update package list (handle GPG errors gracefully)
echo "   Updating package list..."

# Fix Google Cloud SDK GPG key first (common issue that blocks updates)
echo "   Fixing Google Cloud SDK GPG key..."
if curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg 2>/dev/null | \
    sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg 2>/dev/null; then
    echo "   ✅ Google Cloud SDK GPG key fixed"
else
    echo "   ⚠️  Could not fix Google Cloud SDK key (will try to continue anyway)"
fi

# Temporarily allow unauthenticated updates if Google Cloud SDK is the only issue
# This is safe since we're only installing nvidia-container-toolkit, not from that repo
echo "   Updating package lists..."
UPDATE_OUTPUT=$(sudo apt-get update 2>&1)
UPDATE_EXIT=$?

if [ $UPDATE_EXIT -ne 0 ]; then
    # Check if error is only from Google Cloud SDK (non-critical for our purposes)
    if echo "$UPDATE_OUTPUT" | grep -q "NO_PUBKEY C0BA5CE6DC6315A3" && \
       ! echo "$UPDATE_OUTPUT" | grep -qE "nvidia-container-toolkit.*404|nvidia-container-toolkit.*not found|Unable to locate package"; then
        echo "   ⚠️  Google Cloud SDK repo has GPG issues (non-critical)"
        echo "   This won't affect NVIDIA Container Toolkit installation"
        echo "   Continuing..."
    else
        echo "   ❌ Error updating package lists:"
        echo "$UPDATE_OUTPUT" | grep -E "^E:" | head -3
        echo ""
        echo "   💡 Try running: ./fix_gpg_keys.sh"
        echo "   Or manually fix the GPG key issue and try again"
        exit 1
    fi
else
    echo "   ✅ Package lists updated successfully"
fi

# Install
echo "   Installing nvidia-container-toolkit..."
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
echo ""
echo "🔧 Step 5: Configuring Docker..."
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker
echo "   Restarting Docker daemon..."
sudo systemctl restart docker

echo ""
echo "✅ Installation complete!"
echo ""

# Verify installation
echo "🧪 Step 6: Verifying installation..."
echo ""

if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo "✅ GPU access verified in Docker!"
    echo ""
    echo "You can now test your container:"
    echo "  ./test_docker_local.sh"
else
    echo "⚠️  GPU access test failed"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check Docker is running: sudo systemctl status docker"
    echo "  2. Check user is in docker group: groups | grep docker"
    echo "  3. Try: docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi"
    echo ""
    echo "See FIX_GPU_DOCKER.md for more help"
fi
