#!/bin/bash
# Quick script to start the container if it's not running

CONTAINER_NAME="fibroblast-detection-test"
IMAGE_NAME="fibroblast-detection:local-test"

echo "Checking container status..."
echo ""

# Check if container is running
if docker ps | grep -q "$CONTAINER_NAME"; then
    echo "✅ Container is already running"
    docker ps | grep "$CONTAINER_NAME"
    exit 0
fi

# Check if container exists but is stopped
if docker ps -a | grep -q "$CONTAINER_NAME"; then
    echo "⚠️  Container exists but is stopped"
    echo "Removing old container..."
    docker rm -f "$CONTAINER_NAME"
fi

# Check if image exists
if ! docker images | grep -q "fibroblast-detection.*local-test"; then
    echo "❌ Docker image not found: $IMAGE_NAME"
    echo "Please build it first:"
    echo "  ./test_docker_local.sh"
    exit 1
fi

# Check if model artifact exists
if [ ! -f "model.tar.gz" ]; then
    echo "⚠️  model.tar.gz not found. Creating it..."
    mkdir -p model_artifact/code
    cp sagemaker_async_inference.py model_artifact/code/inference.py
    cp requirements-sagemaker.txt model_artifact/requirements.txt
    cd model_artifact
    tar -czf ../model.tar.gz .
    cd ..
    echo "✅ Model artifact created"
fi

echo ""
echo "Starting container..."

# Detect GPU
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    if docker run --rm --runtime=nvidia nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        GPU_FLAG="--runtime=nvidia"
        echo "   Using GPU: --runtime=nvidia"
    elif docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        GPU_FLAG="--gpus all"
        echo "   Using GPU: --gpus all"
    else
        GPU_FLAG=""
        echo "   Using CPU (GPU not accessible)"
    fi
else
    GPU_FLAG=""
    echo "   Using CPU"
fi

# Start container
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$GPU_FLAG" ]; then
    if [ "$GPU_FLAG" = "--runtime=nvidia" ]; then
        docker run -d \
            --name "$CONTAINER_NAME" \
            --runtime=nvidia \
            --shm-size=2g \
            -p 8080:8080 \
            -v "$SCRIPT_DIR/model.tar.gz:/opt/ml/model/model.tar.gz:ro" \
            -e SAGEMAKER_PROGRAM=inference.py \
            -e SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code \
            -e NVIDIA_VISIBLE_DEVICES=all \
            "$IMAGE_NAME" \
            serve
    else
        docker run -d \
            --name "$CONTAINER_NAME" \
            --gpus all \
            --shm-size=2g \
            -p 8080:8080 \
            -v "$SCRIPT_DIR/model.tar.gz:/opt/ml/model/model.tar.gz:ro" \
            -e SAGEMAKER_PROGRAM=inference.py \
            -e SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code \
            -e NVIDIA_VISIBLE_DEVICES=all \
            "$IMAGE_NAME" \
            serve
    fi
else
    docker run -d \
        --name "$CONTAINER_NAME" \
        --shm-size=2g \
        -p 8080:8080 \
        -v "$SCRIPT_DIR/model.tar.gz:/opt/ml/model/model.tar.gz:ro" \
        -e SAGEMAKER_PROGRAM=inference.py \
        -e SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code \
        "$IMAGE_NAME" \
        serve
fi

if [ $? -eq 0 ]; then
    echo "✅ Container started"
    echo ""
    echo "Waiting for server to be ready..."
    sleep 5
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        echo "✅ Container is running"
        echo ""
        echo "Test the endpoint:"
        echo "  python test_docker_endpoint.py <image_path>"
    else
        echo "❌ Container stopped. Check logs:"
        docker logs "$CONTAINER_NAME"
    fi
else
    echo "❌ Failed to start container"
    exit 1
fi
