#!/bin/bash
# Rebuild Docker image with Java and test

echo "=========================================="
echo "Rebuilding Docker Image with Java"
echo "=========================================="
echo ""

# Stop and remove existing container
echo "🧹 Cleaning up old container..."
docker rm -f fibroblast-detection-test 2>/dev/null || true

# Remove old image to force rebuild
echo "🗑️  Removing old image to force rebuild..."
docker rmi fibroblast-detection:local-test 2>/dev/null || echo "   (Image doesn't exist, will build fresh)"

echo ""
echo "🔨 Rebuilding Docker image (this will take a few minutes)..."
echo "   The image now includes Java which is required for the inference server"
echo ""

# Rebuild with the updated Dockerfile
docker build \
    --memory=12g \
    --memory-swap=16g \
    --shm-size=2g \
    -t fibroblast-detection:local-test \
    .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi

echo ""
echo "✅ Image rebuilt successfully!"
echo ""
echo "Now starting container..."
echo ""

# Start container
./start_container.sh

echo ""
echo "Once the container is running, test with:"
echo "  python test_docker_endpoint.py <image_path>"
