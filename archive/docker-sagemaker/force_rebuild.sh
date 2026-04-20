#!/bin/bash
# Force complete rebuild of Docker image with all fixes

echo "=========================================="
echo "FORCE REBUILD - Removing ALL cached layers"
echo "=========================================="
echo ""

# Stop and remove container
echo "🧹 Stopping and removing container..."
docker rm -f fibroblast-detection-test 2>/dev/null || true

# Remove image (force)
echo "🗑️  Removing Docker image..."
docker rmi fibroblast-detection:local-test 2>/dev/null || true

# Remove all build cache
echo "🗑️  Clearing Docker build cache..."
docker builder prune -f

echo ""
echo "🔨 Rebuilding from scratch (no cache)..."
echo "   This will take 10-15 minutes but ensures all fixes are applied"
echo ""

# Build with NO cache to ensure all fixes are applied
docker build \
    --no-cache \
    --memory=12g \
    --memory-swap=16g \
    --shm-size=2g \
    -t fibroblast-detection:local-test \
    .

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "Now start the container:"
    echo "  ./start_container.sh"
else
    echo ""
    echo "❌ Build failed. Check the error messages above."
    exit 1
fi
