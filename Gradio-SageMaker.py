"""
Gradio Frontend for SageMaker Fibroblast Detection Endpoint
This version connects to SageMaker instead of running locally
"""

import os
import boto3
import json
import base64
import time
from PIL import Image
import io
import gradio as gr
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Set via environment variables or update here
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "fibroblast-detection-endpoint")
REGION = os.getenv("AWS_REGION", "us-east-2")
BUCKET_NAME = os.getenv("S3_BUCKET", "fibroblast-detection-bucket")

# Initialize AWS clients with error handling
def get_aws_clients():
    """Get AWS clients with proper error handling"""
    try:
        # Try to get credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        if credentials is None:
            raise ValueError(
                "No AWS credentials found. Please:\n"
                "1. Attach an IAM role to the EC2 instance, OR\n"
                "2. Run 'aws configure' to set up credentials"
            )
        
        # Check if credentials are expired
        if hasattr(credentials, 'expiry') and credentials.expiry:
            from datetime import datetime
            if credentials.expiry < datetime.now(credentials.expiry.tzinfo):
                raise ValueError(
                    "AWS credentials have expired. Please:\n"
                    "1. Refresh your credentials (aws sso login), OR\n"
                    "2. Use an IAM role attached to the EC2 instance"
                )
        
        s3_client = boto3.client('s3', region_name=REGION)
        sagemaker_runtime = boto3.client('sagemaker-runtime', region_name=REGION)
        
        # Test credentials by making a simple call
        try:
            s3_client.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=1)
        except Exception as e:
            if "ExpiredToken" in str(e) or "InvalidToken" in str(e):
                raise ValueError(
                    "AWS token has expired. Please:\n"
                    "1. Refresh credentials: aws sso login (if using SSO), OR\n"
                    "2. Use an IAM role attached to the EC2 instance (recommended)"
                )
            raise
        
        return s3_client, sagemaker_runtime
        
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to initialize AWS clients: {str(e)}")

# Initialize clients (will raise error if credentials are invalid)
try:
    s3_client, sagemaker_runtime = get_aws_clients()
    logger.info("AWS clients initialized successfully")
except ValueError as e:
    logger.error(f"AWS credential error: {e}")
    # Create dummy clients that will fail gracefully
    s3_client = None
    sagemaker_runtime = None

def image_to_base64(image):
    """Convert PIL Image to base64 string"""
    if isinstance(image, Image.Image):
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    return None

def base64_to_image(img_b64):
    """Convert base64 string to PIL Image"""
    img_data = base64.b64decode(img_b64)
    return Image.open(io.BytesIO(img_data))

def invoke_sagemaker_endpoint(image, diameter, denoise, blur):
    """
    Invoke SageMaker async endpoint and return results
    
    Args:
        image: PIL Image
        diameter: Cell diameter parameter
        denoise: Whether to apply denoising
        blur: Whether to apply Gaussian blur
    
    Returns:
        Tuple of (normalized_image, mask_image, histogram_image, stats_text, status_msg)
    """
    status_msg = "🔄 Starting inference..."
    logger.info("Starting inference request")
    
    # Check if AWS clients are initialized
    if s3_client is None or sagemaker_runtime is None:
        error = (
            "❌ AWS credentials not configured.\n\n"
            "Please set up AWS credentials on this EC2 instance:\n"
            "1. **Recommended:** Attach an IAM role to the EC2 instance with:\n"
            "   - AmazonSageMakerFullAccess (or scoped permissions)\n"
            "   - AmazonS3FullAccess (or scoped to your bucket)\n\n"
            "2. **Alternative:** Run 'aws configure' or refresh SSO:\n"
            "   aws sso login --profile your-profile"
        )
        return None, None, None, error, error
    
    try:
        # Convert image to base64
        image_b64 = image_to_base64(image)
        if not image_b64:
            error = "❌ Error: Could not process image"
            return None, None, None, error, error
        
        # Prepare payload
        payload = {
            'image': image_b64,
            'diameter': diameter if diameter else None,
            'denoise': denoise,
            'blur': blur
        }
        
        status_msg = "📤 Uploading image to S3..."
        logger.info("Uploading image to S3")
        
        # Upload input to S3
        input_key = f"async-inference/input/request_{int(time.time())}.json"
        try:
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=input_key,
                Body=json.dumps(payload),
                ContentType='application/json'
            )
        except s3_client.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'ExpiredToken':
                error = (
                    "❌ AWS token has expired.\n\n"
                    "**Quick Fix:**\n"
                    "1. SSH into EC2: `ssh ubuntu@3.150.215.121`\n"
                    "2. Refresh credentials: `aws sso login` (if using SSO)\n"
                    "3. Restart service: `sudo systemctl restart gradio-app`\n\n"
                    "**Better Solution:**\n"
                    "Attach an IAM role to the EC2 instance (credentials never expire)"
                )
                logger.error("ExpiredToken error: AWS credentials expired")
                return None, None, None, error, error
            else:
                raise
        
        input_location = f"s3://{BUCKET_NAME}/{input_key}"
        
        status_msg = "🚀 Invoking SageMaker endpoint..."
        logger.info(f"Invoking endpoint: {ENDPOINT_NAME}")
        
        # Invoke async endpoint
        response = sagemaker_runtime.invoke_endpoint_async(
            EndpointName=ENDPOINT_NAME,
            InputLocation=input_location,
            ContentType='application/json'
        )
        
        output_location = response['OutputLocation']
        
        # Parse S3 path
        parts = output_location.replace('s3://', '').split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        
        # Poll S3 for results (max 5 minutes)
        max_wait = 300
        poll_interval = 3
        start_time = time.time()
        
        status_msg = "⏳ Processing image on GPU (this may take 30-120 seconds)..."
        logger.info(f"Polling for results at: {output_location}")
        
        while time.time() - start_time < max_wait:
            try:
                result_obj = s3_client.get_object(Bucket=bucket, Key=key)
                results = json.loads(result_obj['Body'].read())
                
                status_msg = "✅ Processing complete! Loading results..."
                logger.info("Results received, processing...")
                
                # Extract results
                norm_img = base64_to_image(results['normalized_image'])
                mask_img = base64_to_image(results['segmentation_mask'])
                hist_img = base64_to_image(results['intensity_histogram'])
                
                stats = results['statistics']
                elapsed_time = int(time.time() - start_time)
                stats_text = (
                    f"### 📊 Statistics\n\n"
                    f"**Cell Count:** {stats['cell_count']}\n\n"
                    f"**Confluency:** {stats['confluency']:.2f}%\n\n"
                    f"**Min Intensity:** {stats['min_intensity']}\n\n"
                    f"**Max Intensity:** {stats['max_intensity']}\n\n"
                    f"**Processing Time:** {elapsed_time} seconds"
                )
                
                status_msg = f"✅ Complete! Processed in {elapsed_time} seconds"
                logger.info(f"Inference completed in {elapsed_time} seconds")
                
                return norm_img, mask_img, hist_img, stats_text, status_msg
                
            except s3_client.exceptions.NoSuchKey:
                elapsed = int(time.time() - start_time)
                status_msg = f"⏳ Processing... ({elapsed}s elapsed, typically takes 30-120 seconds)"
                if elapsed % 10 == 0:  # Log every 10 seconds
                    logger.info(f"Still processing... {elapsed}s elapsed")
                time.sleep(poll_interval)
            except Exception as e:
                error = f"❌ Error reading results: {str(e)}"
                import traceback
                logger.error(f"Error reading results: {traceback.format_exc()}")
                return None, None, None, error, error
        
        error = "❌ Timeout: Processing took too long (5 minutes)"
        return None, None, None, error, error
        
    except Exception as e:
        import traceback
        error_msg = f"❌ Error: {str(e)}"
        logger.error(f"Inference error: {traceback.format_exc()}")
        return None, None, None, error_msg, error_msg

# ----------------- Gradio UI -----------------

with gr.Blocks(title="Fibroblast Detection") as demo:
    gr.Markdown("## 🧪 Fibroblast Confluency Detection")
    gr.Markdown("Upload an image to analyze cell confluency using SageMaker endpoint")
    
    with gr.Row():
        with gr.Column():
            image_input = gr.Image(type="pil", label="Upload Image")
            diameter_slider = gr.Slider(
                minimum=5, 
                maximum=100, 
                step=1, 
                value=30, 
                label="Approx. Cell Diameter"
            )
            denoise_checkbox = gr.Checkbox(label="Apply Denoising")
            blur_checkbox = gr.Checkbox(label="Apply Gaussian Blur")
            run_btn = gr.Button("Run Detection", variant="primary")
            
            # Status info
            gr.Markdown(f"**Endpoint:** {ENDPOINT_NAME}  \n**Region:** {REGION}")
        
        with gr.Column():
            status_output = gr.Textbox(
                label="Status",
                value="Ready. Upload an image and click 'Run Detection'.",
                interactive=False,
                lines=2
            )
            stats_output = gr.Markdown(label="Statistics")
            output1 = gr.Image(label="Normalized Image", interactive=True)
            output2 = gr.Image(label="Segmentation Mask", interactive=True, height=300)
            output3 = gr.Image(label="Intensity Histogram", interactive=True)
    
    run_btn.click(
        fn=invoke_sagemaker_endpoint,
        inputs=[image_input, diameter_slider, denoise_checkbox, blur_checkbox],
        outputs=[output1, output2, output3, stats_output, status_output]
    )
    
    # Examples
    gr.Markdown("### Examples")
    gr.Examples(
        examples=[],  # Add example images here if you have them
        inputs=image_input
    )

if __name__ == "__main__":
    # Configuration for deployment
    server_name = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    share = os.getenv("GRADIO_SHARE", "False").lower() == "true"
    
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share
    )
