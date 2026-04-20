# Local Testing Guide

Before deploying to SageMaker, you can test your inference code locally using two methods:

## Method 1: Direct Python Testing (Fastest - Recommended for Development)

This method tests the inference code directly without Docker, perfect for quick iteration.

### Prerequisites

```bash
# Install dependencies
pip install -r requirements-sagemaker.txt
```

### Usage

```bash
# Basic test
python test_local_inference.py path/to/your/image.jpg

# With custom parameters
python test_local_inference.py image.jpg --diameter 30 --denoise --blur

# Custom output directory
python test_local_inference.py image.jpg --output-dir my_results
```

### What it does

1. **Loads the model** - Initializes Cellpose (downloads weights on first run)
2. **Processes input** - Encodes image and prepares request payload
3. **Runs inference** - Executes the same prediction logic as SageMaker
4. **Saves results** - Outputs normalized image, segmentation mask, histogram, and statistics

### Output

Results are saved to `local_test_results/` by default:
- `statistics.json` - Cell count, confluency, intensity stats
- `normalized_image.png` - Preprocessed image
- `segmentation_mask.png` - Cell segmentation results
- `intensity_histogram.png` - Pixel intensity distribution

---

## Method 2: Docker Container Testing (Closest to SageMaker Environment)

This method runs the exact Docker container that will be deployed to SageMaker, ensuring complete compatibility.

### Prerequisites

- Docker installed and configured (see `FIX_DOCKER_PERMISSIONS.md` if needed)
- Docker has access to GPU (if testing GPU inference)

### Step 1: Build and Run Container

```bash
# Build Docker image and start container
./test_docker_local.sh

# Or with a test image
./test_docker_local.sh path/to/your/image.jpg
```

This will:
1. Build the Docker image (same as deployment)
2. Create model artifact (`model.tar.gz`)
3. Start container on port 8080
4. Optionally test with an image

### Step 2: Test the Endpoint

If container is running, test it with:

```bash
# Test with an image
python test_docker_endpoint.py path/to/your/image.jpg

# With parameters
python test_docker_endpoint.py image.jpg --diameter 30 --denoise --blur
```

### Container Management

```bash
# View logs
docker logs -f fibroblast-detection-test

# Stop container
docker stop fibroblast-detection-test

# Remove container
docker rm fibroblast-detection-test

# Check if running
docker ps | grep fibroblast-detection-test
```

### What it tests

- ✅ Docker image builds successfully
- ✅ All dependencies are installed correctly
- ✅ Model loads in container environment
- ✅ Inference server starts and responds
- ✅ HTTP endpoint works correctly
- ✅ Same environment as SageMaker deployment

---

## Comparison

| Feature | Direct Python Test | Docker Test |
|---------|-------------------|-------------|
| **Speed** | ⚡ Fast (no Docker build) | 🐢 Slower (builds image) |
| **Environment** | Your local Python | SageMaker-like container |
| **GPU Support** | ✅ Uses local GPU | ✅ Uses container GPU |
| **Dependencies** | Local pip packages | Container packages |
| **Best For** | Quick iteration | Final validation |

---

## Testing Workflow

### Recommended Development Workflow

1. **Initial Development**: Use Method 1 (Direct Python) for fast iteration
   ```bash
   python test_local_inference.py test_image.jpg
   ```

2. **Before Deployment**: Use Method 2 (Docker) to validate
   ```bash
   ./test_docker_local.sh test_image.jpg
   ```

3. **Deploy to SageMaker**: Once Docker test passes
   ```bash
   python sagemaker_deploy.py
   ```

---

## Troubleshooting

### Method 1 Issues

**Import errors:**
```bash
# Make sure dependencies are installed
pip install -r requirements-sagemaker.txt
```

**Model download fails:**
- Check internet connection
- Cellpose downloads weights on first run (~500MB)
- Model files are cached in `~/.cellpose/models/`

**GPU not detected:**
- Check CUDA installation: `nvidia-smi`
- Cellpose will fall back to CPU automatically

### Method 2 Issues

**GPU not detected in Docker:**
- Error: `nvidia-container-cli: initialization error` or `NVIDIA Driver was not detected`
- **Fix:** Install NVIDIA Container Toolkit:
  ```bash
  ./install_nvidia_container_toolkit.sh
  ```
- Or see `FIX_GPU_DOCKER.md` for detailed instructions
- The script will automatically fall back to CPU if GPU is unavailable

**Docker permission denied:**
- See `FIX_DOCKER_PERMISSIONS.md`
- Or use: `sudo ./test_docker_local.sh`

**Container won't start:**
- Check logs: `docker logs fibroblast-detection-test`
- Verify model artifact exists: `ls -lh model.tar.gz`
- Check port 8080 is available: `lsof -i :8080`

**Connection refused:**
- Wait a few seconds for container to start
- Check container is running: `docker ps`
- Verify port mapping: `docker port fibroblast-detection-test`

**Inference timeout:**
- First inference loads model (takes 1-2 minutes)
- Subsequent requests are faster
- Increase timeout in `test_docker_endpoint.py` if needed

---

## Example Test Images

If you need test images, you can use any from your dataset:

```bash
# Test with a single image
python test_local_inference.py temp_results/AG08498A-P14_T25_10X_0000_TRANS.jpg

# Test with different parameters
python test_local_inference.py image.jpg --diameter 25 --denoise
python test_local_inference.py image.jpg --diameter 35 --blur
```

---

## Next Steps

After successful local testing:

1. ✅ Code works locally
2. ✅ Docker container works
3. 🚀 Deploy to SageMaker: `python sagemaker_deploy.py`

---

## Additional Notes

- **Model Caching**: Cellpose models are cached, so subsequent tests are faster
- **GPU Memory**: Ensure sufficient GPU memory (4GB+ recommended)
- **Disk Space**: Model downloads require ~500MB free space
- **Network**: First run requires internet for model download
