# Pay-Per-Use Architecture: GPU EC2 Start/Stop on Request

Your proposed architecture **does** give you pay-per-use: you only pay for GPU EC2 **while it's running**. When stopped, you pay **$0** for compute (only small EBS storage cost).

## Architecture Overview

```
User → Frontend (EC2, always on, cheap)
    → Backend API (same EC2 or Lambda)
    → Upload image to S3
    → Check GPU EC2 state
    → If stopped → Start GPU EC2 (1–3 min cold start)
    → Wait until instance is running
    → Send inference request to GPU server (HTTP)
    → GPU processes, returns result
    → Backend returns response to User
    → Stop GPU EC2 after idle (e.g. 5–10 min)
```

**Billing:**
- **Frontend EC2:** Always on (e.g. t3.small) — fixed low cost.
- **GPU EC2:** Only charged when **running**. When **stopped**, $0 compute (~$0.10/GB/month for EBS only).
- So you effectively pay **per use** (per running hour), not per API call, but with no cost when idle.

## Tradeoffs

| Benefit | Tradeoff |
|--------|----------|
| Pay only when GPU runs | **Cold start:** 1–3+ minutes to start EC2 and load model. First request after idle is slow. |
| No SageMaker endpoint cost | You operate two EC2s and logic to start/stop. |
| Full control | Need health checks, timeout handling, and “when to stop” policy. |

## Components You Need

### 1. Frontend EC2 (already have this)
- Runs Gradio (or your UI).
- Always on; no GPU.

### 2. GPU EC2 (new or repurpose)
- Same AMI/image as your current GPU setup (e.g. your Docker image or a pre-baked GPU AMI).
- **Instance type:** e.g. `g4dn.xlarge` (same as SageMaker).
- **EBS:** Root volume for OS + model (or mount from S3 at startup).
- **Security group:** Allow HTTP from Frontend EC2 (or VPC internal) on your inference port (e.g. 8080 or 7860).

### 3. Backend API (on Frontend EC2 or Lambda)
- Receives image from user.
- Uploads image to S3 (optional but good for durability and for GPU to pull).
- **Check GPU EC2 state** (e.g. `ec2.describe_instances(InstanceIds=[gpu_instance_id])` → `state['Name']`).
- If `stopped` → **Start instance** (`ec2.start_instances`).
- **Wait until** `state == 'running'` (poll every 10–15 s; typically 1–3 min).
- Optionally wait for **health check**: HTTP GET to `http://<gpu-ec2-ip>:8080/ping` until 200.
- **Send inference request** to GPU (e.g. `http://<gpu-ec2-ip>:8080/invocations` with image or S3 path).
- Return response to user.
- **Schedule stop** after request: e.g. “stop GPU EC2 in 10 minutes if no new requests” (timer or queue).

### 4. “When to stop” policy
- **Option A:** Stop after every request (max savings, cold start every time).
- **Option B:** Stop after N minutes of no requests (e.g. 5–10 min). Balances cost vs latency.
- Use a **single background worker** on Frontend EC2 that:
  - Tracks “last request time” and “GPU in use”.
  - After idle timeout, calls `ec2.stop_instances`.

### 5. Network / addressing
- **Elastic IP** on GPU EC2 so the backend always has a fixed address to call (recommended).
- Or use **private IP** + **instance ID** and resolve private IP after `start_instances` (e.g. from `describe_instances`).
- Prefer **private IP** if Frontend and GPU EC2 are in same VPC (no data transfer cost, more secure).

## High-Level Flow (Pseudocode)

```python
# On Frontend EC2 (or Lambda)
def handle_inference_request(image):
    # 1. Upload image to S3 (optional)
    s3_key = upload_to_s3(image)
    
    # 2. Ensure GPU EC2 is running
    gpu_instance_id = "i-xxxxxxxxx"
    state = get_ec2_state(gpu_instance_id)
    if state != "running":
        start_ec2(gpu_instance_id)
        wait_until_running(gpu_instance_id)  # 1-3 min
        wait_until_healthy(gpu_ec2_url)     # optional: /ping
    
    # 3. Get GPU EC2 address (Elastic IP or from describe_instances)
    gpu_url = get_gpu_ec2_url(gpu_instance_id)
    
    # 4. Send inference request
    result = requests.post(f"{gpu_url}/invocations", json={"image": s3_key or base64}, timeout=300)
    
    # 5. Schedule stop after idle (e.g. 10 min)
    schedule_stop_after_idle(gpu_instance_id, idle_minutes=10)
    
    return result.json()
```

## Minimal Scripts to Add

1. **`start_gpu_ec2.py`** (or in backend): `boto3.client('ec2').start_instances(InstanceIds=[id])`, then poll `describe_instances` until `running`, then optionally poll HTTP `/ping`.
2. **`stop_gpu_ec2.py`** (or cron/worker): `boto3.client('ec2').stop_instances(InstanceIds=[id])`.
3. **Backend endpoint** (e.g. Flask/FastAPI on Frontend EC2): receives upload → calls `handle_inference_request` → returns result.
4. **Gradio (or frontend)** calls this backend URL instead of calling SageMaker directly.

## Summary

- **Yes**, this architecture **can** be used to get **pay-per-use**: you only pay for GPU EC2 when it’s **running**; when it’s **stopped**, you pay $0 compute.
- It’s **not** literally “pay per API call” (billing is still by instance hour), but by starting only when needed and stopping after idle, cost tracks usage.
- Cost is roughly: (hours GPU EC2 is running) × (hourly rate) + (Frontend EC2) + (EBS for stopped GPU) + (S3/transfer).
- Main downside: **cold start** (1–3+ min) when GPU was stopped; you can tune “stop after N min idle” to balance cost vs latency.

If you want, next step can be: a small **backend API** (Flask/FastAPI) on the Frontend EC2 that implements this flow and a **Gradio** client that calls that API instead of SageMaker.
