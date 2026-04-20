# Testing Guide for Gradio-SageMaker Integration

Complete guide to test your Gradio app with the deployed SageMaker endpoint.

## 🧪 Quick Test (Recommended)

### Step 1: Test Endpoint Connection

```bash
# Test endpoint status and S3 access
python test_gradio_sagemaker.py

# Test with an actual image
python test_gradio_sagemaker.py path/to/your/image.jpg
```

This will verify:
- ✅ Endpoint exists and is "InService"
- ✅ S3 bucket is accessible
- ✅ Async inference workflow works
- ✅ Results are returned correctly

### Step 2: Test Gradio Locally

**Before deploying to EC2, test locally:**

```bash
# Install dependencies (if not already installed)
pip install gradio>=4.0.0 boto3>=1.26.0 Pillow>=9.0.0

# Set environment variables (optional, uses defaults if not set)
export SAGEMAKER_ENDPOINT_NAME="fibroblast-detection-endpoint"
export AWS_REGION="us-east-2"
export S3_BUCKET="YOUR_S3_BUCKET"

# Run Gradio
python Gradio-SageMaker.py
```

Then open: `http://localhost:7860`

**Test workflow:**
1. Upload an image
2. Adjust parameters (diameter, denoise, blur)
3. Click "Run Detection"
4. Wait for results (30-120 seconds)
5. Verify all outputs appear:
   - Normalized image
   - Segmentation mask
   - Intensity histogram
   - Statistics

---

## 🔍 Detailed Testing

### Test 1: Endpoint Status

```bash
aws sagemaker describe-endpoint \
    --endpoint-name fibroblast-detection-endpoint \
    --region us-east-2
```

**Expected output:**
- `EndpointStatus: "InService"`
- `EndpointConfigName` should exist

### Test 2: S3 Bucket Access

```bash
# List bucket contents
aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2

# Check async-inference directories
aws s3 ls s3://YOUR_S3_BUCKET/async-inference/ --recursive --region us-east-2
```

### Test 3: Direct API Test

Create a test script:

```python
import boto3
import json
import base64

sagemaker_runtime = boto3.client('sagemaker-runtime', region_name='us-east-2')
s3_client = boto3.client('s3', region_name='us-east-2')

# Load image
with open('test_image.jpg', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

# Upload to S3
payload = {'image': image_b64, 'diameter': 30, 'denoise': False, 'blur': False}
s3_client.put_object(
    Bucket='YOUR_S3_BUCKET',
    Key='async-inference/input/test.json',
    Body=json.dumps(payload)
)

# Invoke
response = sagemaker_runtime.invoke_endpoint_async(
    EndpointName='fibroblast-detection-endpoint',
    InputLocation='s3://YOUR_S3_BUCKET/async-inference/input/test.json',
    ContentType='application/json'
)

print(f"Output: {response['OutputLocation']}")
```

### Test 4: Check CloudWatch Logs

```bash
# View endpoint logs
aws logs tail /aws/sagemaker/Endpoints/fibroblast-detection-endpoint --follow --region us-east-2

# Or in AWS Console:
# CloudWatch → Log groups → /aws/sagemaker/Endpoints/fibroblast-detection-endpoint
```

Look for:
- Model loading messages
- Inference requests
- Errors or exceptions

---

## 🐛 Troubleshooting

### Issue: "Endpoint not found"

**Solution:**
```bash
# Verify endpoint exists
aws sagemaker list-endpoints --region us-east-2

# Check endpoint name matches exactly
# Should be: fibroblast-detection-endpoint
```

### Issue: "Access Denied" to S3

**Solution:**
- Check IAM role/permissions
- Verify bucket name: `YOUR_S3_BUCKET`
- Check region: `us-east-2`

```bash
# Test S3 access
aws s3 ls s3://YOUR_S3_BUCKET/ --region us-east-2
```

### Issue: "Timeout" waiting for results

**Possible causes:**
1. Endpoint is processing (normal - can take 1-5 minutes)
2. Endpoint is stuck/crashed
3. Results not being written to S3

**Check:**
```bash
# Check endpoint status
aws sagemaker describe-endpoint \
    --endpoint-name fibroblast-detection-endpoint \
    --region us-east-2

# Check CloudWatch logs for errors
aws logs tail /aws/sagemaker/Endpoints/fibroblast-detection-endpoint --follow
```

### Issue: "NoSuchKey" when reading results

**This is normal** - the output file doesn't exist until processing completes. The script polls for it.

**If it persists:**
- Check S3 output path permissions
- Verify async inference config in deployment
- Check CloudWatch logs for endpoint errors

### Issue: Gradio shows "Error" but no details

**Enable debug logging:**
```python
# Add to Gradio-SageMaker.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or check the full error:
```python
# The error message should appear in the stats_output field
# Check browser console (F12) for more details
```

---

## ✅ Success Criteria

Your setup is working correctly if:

1. ✅ `test_gradio_sagemaker.py` passes all tests
2. ✅ Endpoint status is "InService"
3. ✅ S3 bucket is accessible
4. ✅ Gradio app loads without errors
5. ✅ Image upload works
6. ✅ "Run Detection" button triggers processing
7. ✅ Results appear within 1-5 minutes:
   - Normalized image displays
   - Segmentation mask displays
   - Histogram displays
   - Statistics show cell count and confluency

---

## 📊 Expected Processing Times

- **Small images (< 1MB):** 30-60 seconds
- **Medium images (1-5MB):** 60-120 seconds
- **Large images (> 5MB):** 2-5 minutes

**Note:** First request may take longer (cold start).

---

## 🚀 Next Steps After Testing

Once testing passes:

1. **Deploy to EC2** (see `EC2_GRADIO_SETUP.md`)
2. **Set up systemd service** (auto-start on boot)
3. **Configure nginx** (reverse proxy)
4. **Set up domain & SSL** (HTTPS)

---

## 📝 Test Checklist

- [ ] Endpoint is "InService"
- [ ] S3 bucket accessible
- [ ] `test_gradio_sagemaker.py` passes
- [ ] Gradio app runs locally
- [ ] Can upload image in Gradio
- [ ] Inference completes successfully
- [ ] All outputs display correctly
- [ ] Statistics are accurate
- [ ] No errors in CloudWatch logs

---

## 💡 Tips

1. **Test with small images first** - Faster feedback
2. **Check CloudWatch logs** - Most errors are visible there
3. **Verify IAM permissions** - Common source of issues
4. **Use test script** - Catches issues before Gradio
5. **Monitor S3** - Check input/output files are created

Good luck! 🎉
