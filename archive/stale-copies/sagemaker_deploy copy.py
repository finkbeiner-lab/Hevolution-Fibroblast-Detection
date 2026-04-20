"""
Script to deploy the Fibroblast Detection model to SageMaker Asynchronous Inference
"""

import boto3
import os

# Check if sagemaker is installed
try:
    import sagemaker
    from sagemaker.model import Model
    from sagemaker.async_inference import AsyncInferenceConfig
    from sagemaker.s3 import S3Uploader
except ImportError as e:
    print("=" * 60)
    print("ERROR: SageMaker SDK not installed!")
    print("=" * 60)
    print("\nPlease install it using:")
    print("  pip install sagemaker boto3")
    print("\nOr install all requirements:")
    print("  pip install -r requirements.txt")
    print("\nThe requirements.txt has been updated to include sagemaker.")
    print("=" * 60)
    raise

# Configuration
ROLE = "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole"  # Update with your IAM role
REGION = "us-east-2"  # Update with your preferred region
BUCKET_NAME = "YOUR_S3_BUCKET"  # Update with your S3 bucket name

# AWS profile for SSO and CLI subprocess calls (default: admin)
AWS_PROFILE = os.environ.get("AWS_PROFILE", "admin")
os.environ["AWS_PROFILE"] = AWS_PROFILE  # So boto3/sagemaker use it too
MODEL_NAME = "fibroblast-detection-model"
ENDPOINT_NAME = "fibroblast-detection-endpoint"

# Instance Configuration
# ml.g4dn.xlarge is the SMALLEST GPU instance available in SageMaker
# GPU instances: ml.g4dn.xlarge (smallest), ml.g4dn.2xlarge, ml.g4dn.4xlarge, etc.
# Cost: ml.g4dn.xlarge ~$0.736/hour (smallest and cheapest GPU option)
INSTANCE_TYPE = "ml.g4dn.xlarge"  # Smallest GPU instance (1 GPU, 4 vCPU, 16GB RAM)

# IAM Permission Check
def check_iam_permissions():
    """
    Check if user has required IAM permissions.
    Note: Your policy allows iam:PassRole with condition iam:PassedToService=sagemaker.amazonaws.com
    which should work. This check verifies the role exists and is accessible.
    """
    import boto3
    sts = boto3.client('sts', region_name=REGION)
    try:
        identity = sts.get_caller_identity()
        current_role = identity.get('Arn', 'Unknown')
        print(f"🔐 Current authenticated role (YOUR SSO ROLE): {current_role}")
        print(f"📋 SageMaker execution role (ROLE variable): {ROLE}")
        print("\n⚠️  IMPORTANT: These are TWO different roles!")
        print("   - Current role: What YOU are authenticated as (needs iam:PassRole permission)")
        print("   - ROLE variable: What SageMaker will USE (the execution role)")
        print(f"\nYour current role '{current_role.split('/')[-1]}' needs permission to pass '{ROLE.split('/')[-1]}' to SageMaker")
        
        # Check if the role exists and is accessible
        # Note: Your policy should allow iam:PassRole to sagemaker.amazonaws.com
        # The actual permission check happens when SageMaker tries to use the role
        iam = boto3.client('iam', region_name=REGION)
        try:
            role_name = ROLE.split('/')[-1]
            role_response = iam.get_role(RoleName=role_name)
            print(f"✅ Role found: {role_name}")
            
            # Check if role has SageMaker trust policy
            trust_policy = role_response['Role']['AssumeRolePolicyDocument']
            if 'sagemaker.amazonaws.com' in str(trust_policy):
                print("✅ Role has SageMaker trust policy")
                return True
            else:
                print("⚠️  Warning: Role may not have SageMaker trust policy")
                print("   The role should allow sagemaker.amazonaws.com to assume it")
                return True  # Continue anyway, let SageMaker API handle it
                
        except iam.exceptions.NoSuchEntityException:
            print(f"❌ Role not found: {role_name}")
            print(f"   Please verify the role ARN: {ROLE}")
            return False
        except Exception as e:
            error_msg = str(e)
            if "AccessDenied" in error_msg or "not authorized" in error_msg.lower():
                print(f"⚠️  Cannot verify role (access denied): {error_msg}")
                print("   This might be okay - your policy should allow iam:PassRole to SageMaker")
                print("   Continuing... (SageMaker will verify permissions during deployment)")
                return True  # Continue, let SageMaker API verify
            else:
                print(f"⚠️  Warning checking role: {e}")
                return True  # Continue anyway
                
    except Exception as e:
        print(f"⚠️  Warning: Could not check IAM permissions: {e}")
        print("   Continuing... (SageMaker will verify permissions during deployment)")
        return True  # Continue anyway, let SageMaker API return the error

# Initialize SageMaker session
# Verify credentials before initializing
def verify_aws_credentials():
    """Verify and display current AWS credentials"""
    sts = boto3.client('sts', region_name=REGION)
    try:
        identity = sts.get_caller_identity()
        current_role = identity.get('Arn', 'Unknown')
        print(f"🔐 Using AWS identity: {current_role}")
        
        # Check if it's AdministratorAccess
        if 'AdministratorAccess' in current_role:
            print("✅ AdministratorAccess detected - should have all permissions")
        elif 'PowerUserAccess' in current_role:
            print("⚠️  PowerUserAccess detected - may need iam:PassRole permission")
        return identity
    except Exception as e:
        print(f"⚠️  Could not verify AWS credentials: {e}")
        return None

# Verify credentials at import time
_aws_identity = verify_aws_credentials()

sess = sagemaker.Session()
s3_client = boto3.client('s3', region_name=REGION)
sagemaker_client = boto3.client('sagemaker', region_name=REGION)

def create_model_artifact():
    """
    Create a model artifact package for SageMaker
    """
    print("Creating model artifact...")
    
    # Create a directory for the model artifact (SageMaker structure)
    os.makedirs('model_artifact', exist_ok=True)
    os.makedirs('model_artifact/code', exist_ok=True)
    
    # Copy the inference script to code/ directory (SageMaker convention)
    os.system('cp sagemaker_async_inference.py model_artifact/code/inference.py')
    
    # Copy SageMaker-specific requirements (no Gradio)
    os.system('cp requirements-sagemaker.txt model_artifact/requirements.txt')
    
    # Create a tar.gz file
    os.system('cd model_artifact && tar -czf ../model.tar.gz . && cd ..')
    
    print("Model artifact created: model.tar.gz")
    print("  Structure: code/inference.py, requirements.txt")

def upload_model_to_s3():
    """
    Upload the model artifact to S3
    """
    print(f"Uploading model to s3://{BUCKET_NAME}/models/{MODEL_NAME}/...")
    
    s3_path = S3Uploader.upload(
        local_path="model.tar.gz",
        desired_s3_uri=f"s3://{BUCKET_NAME}/models/{MODEL_NAME}/",
        sagemaker_session=sess
    )
    
    print(f"Model uploaded to: {s3_path}")
    return s3_path

def cleanup_existing_endpoint():
    """Clean up existing endpoint and config if they exist"""
    import time
    try:
        # Step 1: Delete endpoint first (if it exists)
        try:
            endpoint_info = sagemaker_client.describe_endpoint(EndpointName=ENDPOINT_NAME)
            status = endpoint_info['EndpointStatus']
            print(f"\n⚠️  Existing endpoint found with status: {status}")
            print(f"Deleting existing endpoint...")
            sagemaker_client.delete_endpoint(EndpointName=ENDPOINT_NAME)
            print("✅ Endpoint deletion initiated")
            print("⏳ Waiting 15 seconds for endpoint deletion to process...")
            time.sleep(15)
        except sagemaker_client.exceptions.ResourceNotFound:
            print("ℹ️  No existing endpoint found")
        except Exception as e:
            # Check if it's a "not found" error (could be ValidationException from boto3)
            error_msg = str(e)
            if "Could not find endpoint" in error_msg or "does not exist" in error_msg.lower():
                print("ℹ️  No existing endpoint found")
            else:
                # Other errors - log but continue
                print(f"⚠️  Error checking endpoint: {e}")
                print("   Continuing with deployment...")
        
        # Step 2: Delete endpoint config (can only be deleted after endpoint is gone)
        max_retries = 5
        for i in range(max_retries):
            try:
                sagemaker_client.delete_endpoint_config(EndpointConfigName=ENDPOINT_NAME)
                print("✅ Endpoint config deleted")
                break
            except sagemaker_client.exceptions.ResourceNotFound:
                print("ℹ️  No existing endpoint config found")
                break
            except Exception as e:
                # Check if it's a "not found" error
                error_msg = str(e)
                if "Could not find" in error_msg or "does not exist" in error_msg.lower():
                    print("ℹ️  No existing endpoint config found")
                    break
                # Re-raise if it's not a "not found" error
                raise
            except Exception as e:
                if "Cannot delete" in str(e) or "in use" in str(e).lower():
                    if i < max_retries - 1:
                        wait_time = 10
                        print(f"⚠️  Endpoint config still in use, waiting {wait_time}s... (attempt {i+1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print("⚠️  Could not delete endpoint config - it may still be in use")
                        print("   Run cleanup_failed_endpoint.py first, then retry deployment")
                        raise
                else:
                    print(f"⚠️  Error deleting endpoint config: {e}")
                    break
    except Exception as e:
        if "Cannot delete" not in str(e):
            print(f"⚠️  Error during cleanup: {e}")
            print("   You may need to run cleanup_failed_endpoint.py first")
            raise

def deploy_async_endpoint(model_uri, image_uri=None):
    """
    Deploy the model as an Asynchronous Inference endpoint
    
    Args:
        model_uri: S3 URI of the model artifact
        image_uri: ECR URI of the Docker image (required for Cellpose with GPU)
    """
    print("Deploying Asynchronous Inference endpoint...")
    
    # Clean up any existing endpoint/config first
    cleanup_existing_endpoint()
    
    if not image_uri:
        print("\n⚠️  WARNING: No Docker image URI provided!")
        print("For Cellpose with GPU support, you MUST use a custom Docker image.")
        print("\nPlease:")
        print("1. Build and push Docker image to ECR (see create_custom_docker_image())")
        print("2. Update image_uri parameter with your ECR image URI")
        print("\nExample ECR URI format:")
        print("  YOUR_ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest")
        print("\nContinuing with deployment using Model class...")
        print("(This will fail if image_uri is not provided)")
    
    # Configure async inference
    async_config = AsyncInferenceConfig(
        output_path=f"s3://{BUCKET_NAME}/async-inference/output/",
        max_concurrent_invocations_per_instance=1,  # Adjust based on GPU memory
        # Optional: Remove notification_config if SNS topics don't exist
        # notification_config={
        #     "SuccessTopic": "arn:aws:sns:us-east-2:YOUR_ACCOUNT_ID:async-inference-success",
        #     "ErrorTopic": "arn:aws:sns:us-east-2:YOUR_ACCOUNT_ID:async-inference-error"
        # }
    )
    
    # Use generic Model class (works with custom Docker images)
    # This is better for Cellpose which needs specific dependencies
    if image_uri:
        model = Model(
            image_uri=image_uri,
            model_data=model_uri,
            role=ROLE,
            env={
                'SAGEMAKER_MODEL_SERVER_WORKERS': '1',
                'SAGEMAKER_MODEL_SERVER_TIMEOUT': '600'
            }
        )
    else:
        # Fallback: Try PyTorchModel (may not work without proper setup)
        try:
            from sagemaker.pytorch import PyTorchModel
            model = PyTorchModel(
                model_data=model_uri,
                role=ROLE,
                entry_point='inference.py',
                framework_version='2.0.0',
                py_version='py310',
                env={
                    'SAGEMAKER_MODEL_SERVER_WORKERS': '1',
                    'SAGEMAKER_MODEL_SERVER_TIMEOUT': '600'
                }
            )
        except ImportError:
            raise ValueError(
                "Either provide image_uri (custom Docker image) or ensure PyTorchModel is available. "
                "For Cellpose, custom Docker image is recommended."
            )
    
    # Deploy with async inference config
    print(f"\nDeploying to instance: {INSTANCE_TYPE} (GPU required for Cellpose)")
    print(f"This is the SMALLEST GPU instance available (~$0.736/hour)")
    print("This may take 10-15 minutes...")
    
    try:
        predictor = model.deploy(
            initial_instance_count=1,
            instance_type=INSTANCE_TYPE,  # Smallest GPU instance for Cellpose
            endpoint_name=ENDPOINT_NAME,
            async_inference_config=async_config,
            wait=True
        )
        print(f"\n✅ Endpoint deployed: {ENDPOINT_NAME}")
        return predictor
    except Exception as e:
        error_msg = str(e)
        if "Failed" in error_msg and "health check" in error_msg.lower():
            print("\n" + "=" * 60)
            print("❌ ENDPOINT HEALTH CHECK FAILED")
            print("=" * 60)
            print("\nThe endpoint was created but failed the health check.")
            print("This usually means the container is crashing on startup.")
            print("\nCommon causes:")
            print("1. Model initialization error (Cellpose not loading)")
            print("2. Missing dependencies in Docker image")
            print("3. GPU/CUDA issues")
            print("4. Inference handler errors")
            print("\n📋 Check CloudWatch logs:")
            print(f"   aws logs tail /aws/sagemaker/Endpoints/{ENDPOINT_NAME} --follow")
            print(f"\n   Or in AWS Console:")
            print(f"   CloudWatch → Log groups → /aws/sagemaker/Endpoints/{ENDPOINT_NAME}")
            print("\n💡 The inference script has been updated to:")
            print("   - Initialize model in model_fn (not on each request)")
            print("   - Handle health check pings")
            print("   - Better error handling")
            print("\n   Re-run deployment after checking logs.")
            print("=" * 60)
        raise

def check_docker_permissions():
    """
    Check if Docker is accessible without sudo
    """
    import subprocess
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, timeout=5)
        if result.returncode == 0:
            return True
        else:
            error = result.stderr.decode() if result.stderr else ""
            if "permission denied" in error.lower() or "docker.sock" in error.lower():
                return False
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def setup_ecr_and_push_image():
    """
    Setup ECR repository and push Docker image
    Returns the ECR image URI
    """
    import subprocess
    import re
    
    print("\n" + "=" * 60)
    print("Setting up ECR and pushing Docker image")
    print("=" * 60)
    
    # Check Docker permissions first
    if not check_docker_permissions():
        print("\n⚠️  Docker permission issue detected!")
        print("\n" + "=" * 60)
        print("FIX DOCKER PERMISSIONS")
        print("=" * 60)
        print("\nOption 1: Add user to docker group (RECOMMENDED):")
        print("  sudo usermod -aG docker $USER")
        print("  newgrp docker  # or log out and log back in")
        print("\nOption 2: Use sudo (not recommended for automation):")
        print("  sudo docker build -t fibroblast-detection:latest .")
        print("\nOption 3: Skip Docker and use existing image:")
        print("  python sagemaker_deploy.py --skip-ecr --image-uri YOUR_ECR_URI")
        print("\nAfter fixing, run the script again.")
        print("=" * 60)
        raise RuntimeError("Docker permission denied. Please fix Docker permissions first.")
    
    # Get AWS account ID from role ARN
    account_id_match = re.search(r'arn:aws:iam::(\d+):', ROLE)
    if not account_id_match:
        print("⚠️  Could not extract account ID from role ARN")
        account_id = input("Enter your AWS Account ID: ").strip()
    else:
        account_id = account_id_match.group(1)
    
    ecr_repo = "fibroblast-detection"
    ecr_uri = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{ecr_repo}:latest"
    
    print(f"\nECR Repository: {ecr_repo}")
    print(f"ECR URI: {ecr_uri}")
    print(f"Region: {REGION}")
    
    # Ensure AWS CLI subprocesses use the same profile (for SSO)
    aws_env = os.environ.copy()
    aws_env["AWS_PROFILE"] = AWS_PROFILE

    # Step 1: Create ECR repository
    print("\n1. Creating ECR repository...")
    try:
        subprocess.run([
            'aws', 'ecr', 'create-repository',
            '--repository-name', ecr_repo,
            '--region', REGION
        ], check=True, capture_output=True, env=aws_env)
        print("   ✅ Repository created")
    except subprocess.CalledProcessError as e:
        if "RepositoryAlreadyExistsException" in str(e.stderr):
            print("   ℹ️  Repository already exists")
        else:
            print(f"   ⚠️  Error: {e.stderr.decode()}")
            raise
    
    # Step 2: Login to ECR
    print("\n2. Logging in to ECR...")
    login_cmd = f"aws ecr get-login-password --region {REGION} --profile {AWS_PROFILE} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{REGION}.amazonaws.com"
    result = subprocess.run(login_cmd, shell=True, capture_output=True, text=True, env=aws_env)
    if result.returncode == 0:
        print("   ✅ Logged in to ECR")
    else:
        error_msg = result.stderr if result.stderr else result.stdout
        if "permission denied" in error_msg.lower() or "docker.sock" in error_msg.lower():
            print(f"   ❌ Docker permission error during ECR login")
            print("\n   💡 Fix Docker permissions (see error message above)")
            raise RuntimeError("Docker permission denied for ECR login")
        else:
            print(f"   ❌ Login failed: {error_msg}")
            raise RuntimeError(f"ECR login failed: {error_msg}")
    
    # Step 3: Build Docker image
    print("\n3. Building Docker image...")
    try:
        result = subprocess.run([
                'docker', 'build', 
                '--memory=12g',
                '--memory-swap=16g',
                '--shm-size=2g',
                '-t', 'fibroblast-detection:latest', 
                '.'
            ], capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            print("   ✅ Docker image built")
        else:
            error_msg = result.stderr if result.stderr else result.stdout
            if "permission denied" in error_msg.lower() or "docker.sock" in error_msg.lower():
                print(f"   ❌ Docker permission error: {error_msg}")
                print("\n   💡 Fix Docker permissions:")
                print("      Option 1: Add user to docker group (recommended):")
                print("         sudo usermod -aG docker $USER")
                print("         newgrp docker  # or log out and back in")
                print("\n      Option 2: Run with sudo (not recommended):")
                print("         sudo docker build -t fibroblast-detection:latest .")
                print("\n      Option 3: Skip Docker and use existing image:")
                print("         python sagemaker_deploy.py --skip-ecr --image-uri YOUR_ECR_URI")
                raise RuntimeError("Docker permission denied. See instructions above.")
            else:
                print(f"   ❌ Build failed: {error_msg}")
                raise RuntimeError(f"Docker build failed: {error_msg}")
    except subprocess.TimeoutExpired:
        print("   ❌ Docker build timed out (took more than 10 minutes)")
        raise RuntimeError("Docker build timeout")
    except FileNotFoundError:
        print("   ❌ Docker not found. Please install Docker first.")
        raise RuntimeError("Docker not installed")
    
    # Step 4: Tag image
    print("\n4. Tagging image for ECR...")
    result = subprocess.run(['docker', 'tag', 'fibroblast-detection:latest', ecr_uri],
                          capture_output=True)
    if result.returncode == 0:
        print(f"   ✅ Image tagged as {ecr_uri}")
    else:
        print(f"   ❌ Tagging failed: {result.stderr.decode()}")
        raise RuntimeError("Docker tag failed")
    
    # Step 5: Push to ECR
    print("\n5. Pushing image to ECR (this may take a few minutes)...")
    result = subprocess.run(['docker', 'push', ecr_uri], capture_output=True, text=True, timeout=600)
    if result.returncode == 0:
        print(f"   ✅ Image pushed to ECR")
    else:
        error_msg = result.stderr if result.stderr else result.stdout
        if "permission denied" in error_msg.lower() or "docker.sock" in error_msg.lower():
            print(f"   ❌ Docker permission error during push")
            print("\n   💡 Fix Docker permissions (see error message above)")
            raise RuntimeError("Docker permission denied for push")
        else:
            print(f"   ❌ Push failed: {error_msg}")
            raise RuntimeError(f"Docker push failed: {error_msg}")
    
    print(f"\n✅ ECR setup complete!")
    print(f"Image URI: {ecr_uri}")
    return ecr_uri

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy Fibroblast Detection to SageMaker")
    parser.add_argument('--skip-ecr', action='store_true', 
                       help='Skip ECR setup (use existing image URI)')
    parser.add_argument('--image-uri', type=str, default=None,
                       help='ECR image URI (if already pushed)')
    parser.add_argument('--setup-ecr-only', action='store_true',
                       help='Only setup ECR and push image, do not deploy')
    args = parser.parse_args()
    
    print("=" * 60)
    print("SageMaker Asynchronous Inference Deployment")
    print("=" * 60)
    
    # Step 1: Setup ECR and push Docker image (required for Cellpose)
    image_uri = args.image_uri
    if not args.skip_ecr and not image_uri:
        print("\n📦 Step 1: Setting up ECR and Docker image")
        print("(This is required for Cellpose with GPU support)")
        try:
            image_uri = setup_ecr_and_push_image()
        except Exception as e:
            print(f"\n❌ ECR setup failed: {e}")
            print("\nYou can:")
            print("1. Fix the error and try again")
            print("2. Manually push the image and use --image-uri")
            print("3. Use --skip-ecr if you have an existing image")
            raise
    
    if args.setup_ecr_only:
        print("\n✅ ECR setup complete. Run again without --setup-ecr-only to deploy.")
        exit(0)
    
    # Step 2: Create model artifact
    print("\n📦 Step 2: Creating model artifact")
    create_model_artifact()
    
    # Step 3: Upload to S3
    print("\n📦 Step 3: Uploading model to S3")
    model_uri = upload_model_to_s3()
    
    # Step 4: Check IAM permissions before deploying
    print("\n🔐 Step 4: Checking IAM permissions")
    if not check_iam_permissions():
        print("\n❌ IAM permission check failed. Please fix permissions before deploying.")
        print("\nTo fix:")
        print("1. Contact your AWS administrator")
        print("2. Ask them to add 'iam:PassRole' permission for the SageMaker role")
        print("3. Or attach 'AmazonSageMakerFullAccess' policy to your user/role")
        exit(1)
    
    # Step 5: Deploy endpoint
    print("\n🚀 Step 5: Deploying endpoint")
    try:
        predictor = deploy_async_endpoint(model_uri, image_uri=image_uri)
    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg and "iam:PassRole" in error_msg:
            import boto3
            sts = boto3.client('sts', region_name=REGION)
            current_identity = sts.get_caller_identity()
            current_role = current_identity.get('Arn', 'Unknown')
            
            print("\n" + "=" * 60)
            print("❌ IAM PERMISSION ERROR - iam:PassRole")
            print("=" * 60)
            print("\n🔍 Understanding the error:")
            print(f"   Your authenticated role: {current_role}")
            print(f"   SageMaker execution role: {ROLE}")
            print("\n   The error shows YOUR current SSO role (from AWS credentials)")
            print("   trying to pass the SageMaker execution role to SageMaker.")
            print("\n   These are TWO different roles:")
            print("   1. YOUR role (SSO): What you're logged in as")
            print("   2. ROLE variable: What SageMaker will use (execution role)")
            print(f"\n❌ Your SSO role '{current_role.split('/')[-1]}' cannot pass '{ROLE.split('/')[-1]}' to SageMaker")
            print("\n💡 Solutions:")
            print("\nOption 1: Ask admin to add explicit iam:PassRole permission:")
            print("   Add this policy to your SSO role:")
            print("   {")
            print('     "Version": "2012-10-17",')
            print('     "Statement": [')
            print('       {')
            print('         "Effect": "Allow",')
            print('         "Action": "iam:PassRole",')
            print(f'         "Resource": "{ROLE}"')
            print('       }')
            print('     ]')
            print('   }')
            print("\nOption 2: Switch to AdministratorAccess SSO role for deployment")
            print("   (if you have access to it)")
            print("\nOption 3: Ask admin to verify 'AllowPassRoleToSageMaker' policy")
            print("   is attached to your SSO role and working correctly")
            print("=" * 60)
        raise
    
    print("\n" + "=" * 60)
    print("✅ Deployment Complete!")
    print("=" * 60)
    print(f"Endpoint Name: {ENDPOINT_NAME}")
    print(f"Region: {REGION}")
    print(f"Instance: {INSTANCE_TYPE} (GPU - Smallest available)")
    print("=" * 60)
    
    print("\nTo invoke the endpoint asynchronously:")
    print("""
    import boto3
    import json
    import base64
    
    sagemaker_runtime = boto3.client('sagemaker-runtime', region_name='us-east-2')
    
    # Prepare input
    with open('image.jpg', 'rb') as f:
        image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    payload = {
        'image': image_b64,
        'diameter': 30,
        'denoise': False,
        'blur': False
    }
    
    # Invoke async endpoint
    response = sagemaker_runtime.invoke_endpoint_async(
        EndpointName='fibroblast-detection-endpoint',
        InputLocation=f's3://{BUCKET_NAME}/async-inference/input/request.json',
        ContentType='application/json'
    )
    
    output_location = response['OutputLocation']
    print(f"Results will be available at: {output_location}")
    """)
