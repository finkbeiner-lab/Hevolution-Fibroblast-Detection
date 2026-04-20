#!/bin/bash
# Quick script to check container status

echo "Checking Docker container status..."
echo ""

# Check if container exists and is running
if docker ps | grep -q fibroblast-detection-test; then
    echo "✅ Container is RUNNING"
    echo ""
    docker ps | grep fibroblast-detection-test
    echo ""
    echo "Container logs (last 20 lines):"
    docker logs --tail 20 fibroblast-detection-test
elif docker ps -a | grep -q fibroblast-detection-test; then
    echo "⚠️  Container exists but is NOT running"
    echo ""
    docker ps -a | grep fibroblast-detection-test
    echo ""
    echo "Container logs:"
    docker logs fibroblast-detection-test
    echo ""
    echo "To start it:"
    echo "  ./test_docker_local.sh"
else
    echo "❌ Container does not exist"
    echo ""
    echo "To create and start it:"
    echo "  ./test_docker_local.sh"
fi

echo ""
echo "To test the endpoint:"
echo "  python test_docker_endpoint.py <original_image.jpg>"
echo ""
echo "Note: Use the ORIGINAL image file (.jpg), not the mask output (.png)"
