FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

WORKDIR /opt/ml

# Install system dependencies (including Java for Multi-Model Server)
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    openjdk-11-jdk-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# Upgrade pip and install build tools
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

# Copy constraints file to lock NumPy version (must be before any package installs)
COPY constraints.txt /tmp/constraints.txt

# Install core scientific computing libraries FIRST (required by PyTorch and Cellpose)
# CRITICAL: PyTorch 2.0.1 requires NumPy < 2.0 (NumPy 2.x has breaking changes)
# Pin to EXACT NumPy 1.24.4 (tested compatible with PyTorch 2.0.1)
# Install NumPy FIRST and lock it to prevent other packages from upgrading it
RUN pip3 install --no-cache-dir "numpy==1.24.4"

# Verify NumPy version is correct (must be 1.x)
RUN python3 -c "import numpy; assert numpy.__version__.startswith('1.'), f'NumPy version {numpy.__version__} is incompatible! Must be 1.x'; print(f'✅ NumPy locked to: {numpy.__version__}')"

# Install SciPy (must be compatible with NumPy 1.24.4)
# SciPy 1.11+ requires NumPy 2.x, so we need SciPy < 1.11
# Use constraints file to prevent NumPy upgrade
RUN pip3 install --no-cache-dir \
    --constraint /tmp/constraints.txt \
    "scipy>=1.9.0,<1.11.0" && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4'; print('✅ NumPy still 1.24.4 after SciPy')"

# Install PyTorch with CUDA (must come after numpy, and will link against it)
RUN pip3 install --no-cache-dir \
    torch==2.0.1 \
    torchvision==0.15.2 \
    --index-url https://download.pytorch.org/whl/cu118

# CRITICAL: Ensure NumPy 1.x is still locked (prevent any upgrades)
# Reinstall to ensure proper linking with PyTorch
RUN pip3 install --no-cache-dir --force-reinstall --no-deps "numpy==1.24.4" && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4', f'NumPy version changed to {numpy.__version__}!'; print('✅ NumPy still locked to 1.24.4')"

# CRITICAL VERIFICATION: Test NumPy-PyTorch integration (fail build if broken)
RUN python3 << 'VERIFY_EOF'
import sys
import numpy as np
import torch

print("Testing NumPy-PyTorch integration...")
try:
    # Create NumPy array
    x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    print(f"Created NumPy array: {x}")
    
    # Convert to PyTorch tensor
    y = torch.from_numpy(x)
    print(f"Converted to PyTorch tensor: {y}")
    
    # Convert back to NumPy
    z = y.numpy()
    print(f"Converted back to NumPy: {z}")
    
    # Verify values match
    if np.allclose(x, z):
        print("✅ NumPy-PyTorch integration WORKS - this is critical for Cellpose!")
    else:
        print(f"❌ Values don't match: {x} vs {z}")
        sys.exit(1)
        
except RuntimeError as e:
    if "Numpy is not available" in str(e):
        print(f"❌ CRITICAL ERROR: {e}")
        print("   PyTorch cannot access NumPy - Cellpose will fail!")
        print("   This means NumPy version is incompatible with PyTorch 2.0.1")
        sys.exit(1)
    else:
        raise
except Exception as e:
    print(f"❌ NumPy-PyTorch integration test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
VERIFY_EOF

# Install image processing libraries (with NumPy constraint)
RUN pip3 install --no-cache-dir \
    --constraint /tmp/constraints.txt \
    Pillow>=9.5.0 \
    opencv-python-headless>=4.8.0 \
    scikit-image>=0.21.0 && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4'; print('✅ NumPy still 1.24.4 after image libs')"

# Install visualization libraries (with NumPy constraint)
RUN pip3 install --no-cache-dir \
    --constraint /tmp/constraints.txt \
    matplotlib>=3.7.0 && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4'; print('✅ NumPy still 1.24.4 after matplotlib')"

# Install Cellpose and its dependencies (with NumPy constraint)
# Cellpose 3.0+ requires: torch, numpy, scipy, tqdm, natsort, fastremap
RUN pip3 install --no-cache-dir \
    --constraint /tmp/constraints.txt \
    cellpose>=3.0.0 && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4'; print('✅ NumPy still 1.24.4 after Cellpose')"

# Install SageMaker Inference Toolkit (with NumPy constraint)
RUN pip3 install --no-cache-dir \
    --constraint /tmp/constraints.txt \
    sagemaker-inference>=1.9.0 \
    multi-model-server && \
    python3 -c "import numpy; assert numpy.__version__ == '1.24.4'; print('✅ NumPy still 1.24.4 after SageMaker')"

# FINAL: Verify NumPy is still locked
RUN python3 -c "import numpy; assert numpy.__version__ == '1.24.4', f'FINAL CHECK FAILED: NumPy is {numpy.__version__}, expected 1.24.4'; print(f'✅ FINAL NumPy version: {numpy.__version__}')"

# Comprehensive verification of all dependencies
RUN python3 << 'EOF'
import sys

# Core libraries
try:
    import numpy as np
    print(f"✅ NumPy: {np.__version__}")
    # CRITICAL: Verify NumPy is 1.x, not 2.x
    if not np.__version__.startswith('1.'):
        print(f"❌ CRITICAL: NumPy version {np.__version__} is incompatible!")
        print("   PyTorch 2.0.1 requires NumPy < 2.0")
        print("   This will cause 'Numpy is not available' errors!")
        sys.exit(1)
    if np.__version__ != '1.24.4':
        print(f"⚠️  Warning: NumPy is {np.__version__}, expected 1.24.4")
        print("   This may still work, but 1.24.4 is recommended")
except ImportError as e:
    print(f"❌ NumPy failed: {e}")
    sys.exit(1)

try:
    import scipy
    print(f"✅ SciPy: {scipy.__version__}")
except ImportError as e:
    print(f"❌ SciPy failed: {e}")
    sys.exit(1)

# PyTorch
try:
    import torch
    print(f"✅ PyTorch: {torch.__version__}")
    print(f"   CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   CUDA version: {torch.version.cuda}")
        print(f"   GPU device: {torch.cuda.get_device_name(0)}")
except ImportError as e:
    print(f"❌ PyTorch failed: {e}")
    sys.exit(1)

# PyTorch-NumPy integration test - CRITICAL for Cellpose
try:
    import numpy as np
    import torch
    # Test basic conversion
    x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    y = torch.from_numpy(x)
    result = y.numpy().tolist()
    if abs(result[0] - 1.0) < 0.001 and abs(result[1] - 2.0) < 0.001:
        print("✅ PyTorch-NumPy integration works")
    else:
        print(f"❌ PyTorch-NumPy integration test failed: expected [1.0, 2.0, 3.0], got {result}")
        sys.exit(1)
except RuntimeError as e:
    if "Numpy is not available" in str(e):
        print(f"❌ CRITICAL: PyTorch cannot access NumPy: {e}")
        print("   This will cause Cellpose to fail at runtime!")
        sys.exit(1)
    else:
        print(f"⚠️  PyTorch-NumPy integration test failed: {e}")
        print("   (May be okay during build without GPU)")
except Exception as e:
    print(f"❌ PyTorch-NumPy integration test failed: {e}")
    import traceback
    traceback.print_exc()
    # For NumPy integration, we should fail the build if it doesn't work
    if "numpy" in str(e).lower() or "Numpy" in str(e):
        sys.exit(1)

# Image processing
try:
    from PIL import Image
    print(f"✅ Pillow: {Image.__version__}")
except ImportError as e:
    print(f"❌ Pillow failed: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✅ OpenCV: {cv2.__version__}")
except ImportError as e:
    print(f"❌ OpenCV failed: {e}")
    sys.exit(1)

try:
    import skimage
    print(f"✅ scikit-image: {skimage.__version__}")
except ImportError as e:
    print(f"❌ scikit-image failed: {e}")
    sys.exit(1)

# Visualization
try:
    import matplotlib
    print(f"✅ Matplotlib: {matplotlib.__version__}")
except ImportError as e:
    print(f"❌ Matplotlib failed: {e}")
    sys.exit(1)

# Cellpose
try:
    from cellpose import models
    print("✅ Cellpose imported successfully")
    # Test CellposeModel instantiation (without GPU to avoid device issues during build)
    # Just verify the class exists
    assert hasattr(models, 'CellposeModel'), "CellposeModel not found in models"
    print("✅ CellposeModel class available")
except ImportError as e:
    print(f"❌ Cellpose import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"❌ Cellpose verification failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# SageMaker
try:
    import sagemaker_inference
    print("✅ sagemaker-inference imported successfully")
except ImportError as e:
    print(f"❌ sagemaker-inference failed: {e}")
    sys.exit(1)

print("\n✅ All dependencies verified successfully!")
EOF

# Copy serve script
COPY serve /usr/local/bin/serve
RUN chmod +x /usr/local/bin/serve

# Set environment variables
ENV SAGEMAKER_PROGRAM=inference.py
ENV SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code
ENV PYTHONUNBUFFERED=TRUE

# Expose port
EXPOSE 8080

# Default command (can be overridden)
CMD ["serve"]
