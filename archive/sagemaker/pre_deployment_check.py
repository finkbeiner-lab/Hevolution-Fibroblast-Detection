#!/usr/bin/env python3
"""
Pre-deployment checklist for SageMaker deployment
Verifies all configurations and files are ready
"""

import os
import sys
import json
import subprocess
from pathlib import Path

print("=" * 60)
print("SageMaker Pre-Deployment Checklist")
print("=" * 60)
print()

errors = []
warnings = []
checks_passed = 0

# Check 1: Verify inference code exists and is correct
print("1. Checking inference code...")
if os.path.exists("sagemaker_async_inference.py"):
    with open("sagemaker_async_inference.py", 'r') as f:
        content = f.read()
        # Check for critical components
        if "def model_fn" in content and "def input_fn" in content and "def predict_fn" in content:
            if "CellposeModel" in content:
                if "use_bfloat16=False" in content:
                    print("   ✅ Inference code has all required functions")
                    print("   ✅ Uses CellposeModel (Cellpose 3.0+)")
                    print("   ✅ BFloat16 disabled")
                    checks_passed += 1
                else:
                    errors.append("Inference code missing use_bfloat16=False")
            else:
                errors.append("Inference code doesn't use CellposeModel")
        else:
            errors.append("Inference code missing required functions (model_fn, input_fn, predict_fn)")
else:
    errors.append("sagemaker_async_inference.py not found")

# Check 2: Verify Dockerfile exists and has all dependencies
print("\n2. Checking Dockerfile...")
if os.path.exists("Dockerfile"):
    with open("Dockerfile", 'r') as f:
        dockerfile = f.read()
        required = [
            "numpy==1.24.4",
            "torch==2.0.1",
            "cellpose>=3.0.0",
            "sagemaker-inference",
            "openjdk-11-jdk-headless",
            "SAGEMAKER_PROGRAM=inference.py"
        ]
        missing = [req for req in required if req not in dockerfile]
        if not missing:
            print("   ✅ Dockerfile has all required dependencies")
            checks_passed += 1
        else:
            errors.append(f"Dockerfile missing: {', '.join(missing)}")
else:
    errors.append("Dockerfile not found")

# Check 3: Verify constraints.txt exists
print("\n3. Checking constraints.txt...")
if os.path.exists("constraints.txt"):
    with open("constraints.txt", 'r') as f:
        if "numpy==1.24.4" in f.read():
            print("   ✅ constraints.txt exists and locks NumPy version")
            checks_passed += 1
        else:
            warnings.append("constraints.txt doesn't lock NumPy to 1.24.4")
else:
    errors.append("constraints.txt not found")

# Check 4: Verify serve script exists
print("\n4. Checking serve script...")
if os.path.exists("serve"):
    print("   ✅ serve script exists")
    checks_passed += 1
else:
    errors.append("serve script not found")

# Check 5: Verify model artifact structure
print("\n5. Checking model artifact structure...")
if os.path.exists("model_artifact/code/inference.py"):
    # Check if it matches the main inference file
    with open("sagemaker_async_inference.py", 'r') as f1:
        main_content = f1.read()
    with open("model_artifact/code/inference.py", 'r') as f2:
        artifact_content = f2.read()
    
    # Check for key differences
    if "use_bfloat16=False" in artifact_content and "CellposeModel" in artifact_content:
        print("   ✅ Model artifact code is up to date")
        checks_passed += 1
    else:
        warnings.append("Model artifact may be outdated - run: cp sagemaker_async_inference.py model_artifact/code/inference.py && cd model_artifact && tar -czf ../model.tar.gz .")
    
    if os.path.exists("model_artifact/requirements.txt"):
        print("   ✅ Model artifact has requirements.txt")
    else:
        warnings.append("model_artifact/requirements.txt missing")
else:
    warnings.append("model_artifact/code/inference.py not found - will be created during deployment")

# Check 6: Verify deployment configuration
print("\n6. Checking deployment configuration...")
if os.path.exists("sagemaker_deploy.py"):
    with open("sagemaker_deploy.py", 'r') as f:
        deploy_content = f.read()
        # Check for configuration
        if 'ROLE = "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole"' in deploy_content:
            print("   ✅ IAM Role configured")
        else:
            warnings.append("IAM Role may need to be updated")
        
        if 'REGION = "us-east-2"' in deploy_content:
            print("   ✅ Region configured: us-east-2")
        else:
            warnings.append("Region may need to be updated")
        
        if 'BUCKET_NAME = "YOUR_S3_BUCKET"' in deploy_content:
            print("   ✅ S3 Bucket configured")
        else:
            warnings.append("S3 Bucket name may need to be updated")
        
        checks_passed += 1
else:
    errors.append("sagemaker_deploy.py not found")

# Check 7: Verify AWS credentials
print("\n7. Checking AWS credentials...")
try:
    result = subprocess.run(['aws', 'sts', 'get-caller-identity'], 
                          capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        identity = json.loads(result.stdout)
        print(f"   ✅ AWS credentials valid")
        print(f"      Account: {identity.get('Account', 'N/A')}")
        print(f"      User/Role: {identity.get('Arn', 'N/A').split('/')[-1]}")
        checks_passed += 1
    else:
        if "ExpiredTokenException" in result.stderr:
            errors.append("AWS credentials expired - run: ./refresh_aws_credentials.sh")
        else:
            errors.append(f"AWS credentials error: {result.stderr}")
except FileNotFoundError:
    errors.append("AWS CLI not installed or not in PATH")
except subprocess.TimeoutExpired:
    warnings.append("AWS credentials check timed out")

# Check 8: Verify Docker is available
print("\n8. Checking Docker...")
try:
    result = subprocess.run(['docker', '--version'], 
                          capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"   ✅ Docker installed: {result.stdout.strip()}")
        
        # Check if user can run docker
        result2 = subprocess.run(['docker', 'ps'], 
                                capture_output=True, timeout=5)
        if result2.returncode == 0:
            print("   ✅ Docker accessible (no permission issues)")
            checks_passed += 1
        else:
            if "permission denied" in result2.stderr.decode().lower():
                errors.append("Docker permission denied - see FIX_DOCKER_PERMISSIONS.md")
            else:
                warnings.append("Docker may have permission issues")
    else:
        errors.append("Docker not working properly")
except FileNotFoundError:
    errors.append("Docker not installed")
except subprocess.TimeoutExpired:
    warnings.append("Docker check timed out")

# Check 9: Verify model.tar.gz exists (optional - will be created)
print("\n9. Checking model.tar.gz...")
if os.path.exists("model.tar.gz"):
    size = os.path.getsize("model.tar.gz") / (1024 * 1024)  # MB
    print(f"   ✅ model.tar.gz exists ({size:.1f} MB)")
    if size < 1:
        warnings.append("model.tar.gz seems very small - may be incomplete")
    checks_passed += 1
else:
    warnings.append("model.tar.gz not found - will be created during deployment")

# Check 10: Verify no hardcoded local paths
print("\n10. Checking for hardcoded paths...")
if os.path.exists("sagemaker_async_inference.py"):
    with open("sagemaker_async_inference.py", 'r') as f:
        content = f.read()
        bad_paths = ['/home/', '/gladstone/', 'localhost', '127.0.0.1']
        found = [path for path in bad_paths if path in content]
        if not found:
            print("   ✅ No hardcoded local paths found")
            checks_passed += 1
        else:
            warnings.append(f"Potential hardcoded paths found: {', '.join(found)}")

# Summary
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
print(f"✅ Checks passed: {checks_passed}/10")

if warnings:
    print(f"\n⚠️  Warnings ({len(warnings)}):")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning}")

if errors:
    print(f"\n❌ Errors ({len(errors)}):")
    for i, error in enumerate(errors, 1):
        print(f"   {i}. {error}")
    print("\n❌ Please fix errors before deploying!")
    sys.exit(1)
elif warnings:
    print("\n⚠️  Review warnings above, but deployment should work")
    sys.exit(0)
else:
    print("\n✅ All checks passed! Ready for deployment.")
    print("\nNext steps:")
    print("  1. Refresh AWS credentials if needed: ./refresh_aws_credentials.sh")
    print("  2. Deploy: python sagemaker_deploy.py")
    sys.exit(0)
