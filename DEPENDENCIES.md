# Complete Dependency List

This document lists all dependencies required for the Fibroblast Detection SageMaker deployment.

## System Dependencies (apt)

- `python3.10` - Python interpreter
- `python3-pip` - Python package manager
- `libgl1-mesa-glx` - OpenGL libraries (for OpenCV)
- `libglib2.0-0` - GLib library
- `libsm6` - X11 Session Management library
- `libxext6` - X11 miscellaneous extension library
- `libxrender-dev` - X Rendering Extension library
- `libgomp1` - OpenMP library (for parallel processing)
- `openjdk-11-jdk-headless` - Java JDK (for Multi-Model Server)
- `curl` - HTTP client (for health checks)

## Python Dependencies (pip)

### Core Scientific Computing (installed first)
- `numpy>=1.23.0` - Numerical computing (required by PyTorch)
- `scipy>=1.9.0` - Scientific computing library

### Deep Learning
- `torch==2.0.1` - PyTorch framework (with CUDA 11.8 support)
- `torchvision==0.15.2` - PyTorch vision utilities

### Image Processing
- `Pillow>=9.5.0` - PIL/Pillow for image handling
- `opencv-python-headless>=4.8.0` - OpenCV (headless, no GUI)
- `scikit-image>=0.21.0` - Image processing algorithms

### Visualization
- `matplotlib>=3.7.0` - Plotting and visualization

### Cell Segmentation
- `cellpose>=3.0.0` - Cellpose segmentation library
  - Automatically installs: `tqdm`, `natsort`, `fastremap`, `numba`, `torch`, `numpy`, `scipy`

### SageMaker Infrastructure
- `sagemaker-inference>=1.9.0` - SageMaker inference toolkit
- `multi-model-server` - Multi-Model Server (Java-based)

## Import Analysis

From `sagemaker_async_inference.py`:
- `os` - Standard library
- `json` - Standard library
- `numpy` - ✅ Installed
- `PIL` (Pillow) - ✅ Installed
- `cv2` (OpenCV) - ✅ Installed
- `matplotlib.pyplot` - ✅ Installed
- `io` - Standard library
- `base64` - Standard library
- `logging` - Standard library
- `cellpose.models` - ✅ Installed
- `torch` - ✅ Installed (imported in model_fn)

## Installation Order (Critical)

1. **System packages** (apt) - Base libraries
2. **NumPy & SciPy** - Core scientific libraries (must be before PyTorch)
3. **PyTorch** - Deep learning framework (requires NumPy)
4. **Image processing** - PIL, OpenCV, scikit-image
5. **Visualization** - Matplotlib
6. **Cellpose** - Segmentation library (requires PyTorch, NumPy, SciPy)
7. **SageMaker** - Inference toolkit (installed last)

## Verification

The Dockerfile includes comprehensive verification that:
- ✅ All packages import successfully
- ✅ PyTorch can use NumPy arrays (critical integration)
- ✅ CUDA is available and working
- ✅ CellposeModel class is available
- ✅ All version numbers are displayed

## Common Issues Fixed

1. **NumPy before PyTorch** - PyTorch requires NumPy to be installed first
2. **Java for MMS** - Multi-Model Server requires Java
3. **OpenCV headless** - No GUI dependencies in container
4. **Comprehensive verification** - Catches missing dependencies during build
