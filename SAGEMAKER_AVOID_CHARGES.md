# How to Avoid SageMaker Charges When Not in Use

Your async inference endpoint uses **one instance (ml.g4dn.xlarge)** that runs 24/7 by default, so you are charged whenever the endpoint exists and is in service.

## Option 1: Delete the Endpoint When Not in Use (Recommended)

**When you're done using the app:** delete the endpoint. You pay **$0** while it’s deleted.

**When you need it again:** run the deploy script again (takes about 10–15 minutes).

### Stop charges (delete endpoint)

```bash
# Use the cleanup script
python cleanup_failed_endpoint.py
```

Or with AWS CLI:

```bash
export AWS_PROFILE=admin   # if using SSO

# Delete endpoint
aws sagemaker delete-endpoint --endpoint-name fibroblast-detection-endpoint --region us-east-2

# Wait ~2 minutes, then delete endpoint config
aws sagemaker delete-endpoint-config --endpoint-config-name fibroblast-detection-endpoint --region us-east-2
```

### Start again (re-deploy)

```bash
aws sso login --profile admin
python sagemaker_deploy.py --skip-ecr --image-uri 098023138344.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
```

(`--skip-ecr` skips Docker build/push and reuses the existing image.)

---

## Option 2: Scale to Zero (Newer Feature – Different Setup)

AWS supports **scale to zero** for endpoints that use **inference components** (newer API). Your current deployment uses the classic async inference setup (single production variant), which **does not** support scale-to-zero.

To use scale-to-zero you would need to:

- Re-deploy using **inference components** and **managed instance scaling** with `MinInstanceCount = 0`.
- Configure Application Auto Scaling with `min-capacity 0` and a step scaling policy + CloudWatch alarm for scale-out from zero.

That would require changing how the endpoint is created (different from the current `sagemaker_deploy.py` flow). If you want to go that route, we can outline the exact API/CLI steps.

---

## Option 3: Keep Endpoint but Reduce Cost

If you must keep the endpoint available 24/7:

- You already use the smallest GPU instance (**ml.g4dn.xlarge**), so you can’t shrink instance size further.
- You can’t “pause” an endpoint; it’s either running (and billed) or deleted.

So the only way to **stop compute charges** is to **delete the endpoint** when you don’t need it.

---

## Summary

| Goal                         | What to do                                                                 |
|-----------------------------|----------------------------------------------------------------------------|
| **No charge when idle**     | Delete endpoint: `python cleanup_failed_endpoint.py` (or CLI commands above). |
| **Use the app again**       | Re-deploy: `python sagemaker_deploy.py --skip-ecr --image-uri ...`         |
| **Scale to zero in future** | Re-deploy using inference components + scale-to-zero (different setup).    |

**Bottom line:** To make sure you’re **not charged when no requests come in**, delete the endpoint when you’re not using it. There is no extra charge for the model artifact in S3 or the ECR image; you only pay for endpoint compute when the endpoint exists and is in service.
