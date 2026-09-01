# RunPod Serverless deployment

Architecture:

```
Browser  --->  Gradio UI on AWS (Gradio-RunPod.py)  --HTTPS-->  RunPod Serverless
                                                                 (runpod_handler.py)
```

The AWS box only handles the UI. Every "Run Detection" click posts the
uploaded image (base64) to your RunPod Serverless endpoint and renders the
JSON response.

> **Before deploying anything, test for free.** `LOCAL_INFERENCE=1` runs this
> same UI against the worker code in-process, no endpoint and no GPU spend.
> See [LOCAL_TESTING.md](./LOCAL_TESTING.md); the branch-to-production
> workflow is in [WORKFLOW.md](./WORKFLOW.md).

---

## 1. Build and push the worker image

RunPod Serverless pulls a Docker image from any public/private registry
(Docker Hub, GHCR, ECR, etc.). Build it once, push it, then point the
endpoint at the tag.

Tag the image with the **commit SHA it was built from**, not `latest`. A
mutable `latest` tag leaves nothing to roll back to; a SHA tag makes rollback a
console repoint with no rebuild (see [WORKFLOW.md](./WORKFLOW.md)).

```bash
# From the repo root, on the commit you want to ship
SHA=$(git rev-parse --short HEAD)

docker build --platform linux/amd64 -f Dockerfile.runpod \
  --build-arg REPO_REF="$SHA" \
  -t <your-dockerhub-user>/fibroblast-runpod:"$SHA" .

docker push <your-dockerhub-user>/fibroblast-runpod:"$SHA"
```

Notes:
- `--platform linux/amd64` matters when building on an Apple Silicon Mac;
  RunPod fleets are x86.
- The Dockerfile does **not** copy your working tree. It clones `REPO_URL` at
  `REPO_REF` from GitHub, so **commit and push before building** or the image
  will not contain your change.
- Base image is `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
  (torch 2.8 / NumPy 2).
- Cellpose `cyto3` weights are **not** baked into the image. They are read
  from the Network Volume at `$CELLPOSE_LOCAL_MODELS_PATH`
  (`/runpod-volume/cellpose_models`), which you pre-populate once — see
  section 6. Without a volume, each cold start re-downloads them.

## 2. Create the Serverless endpoint

1. Go to **RunPod Console -> Serverless -> New Endpoint**.
2. **Container Image:** `docker.io/<your-dockerhub-user>/fibroblast-runpod:<SHA>`
3. **Container Disk:** 5 GB is plenty.
4. **GPU Types:** pick whatever fits your budget (RTX A4000 / A5000 is fine
   for Cellpose on typical microscopy tiles).
5. **Max Workers:** start with 1-3 for testing.
   **Min Workers: 0** — anything higher bills continuously while idle.
6. **Idle Timeout:** 5-30 s (this controls how quickly workers scale down).
7. **Container Start Command:** leave blank (the `CMD` in the Dockerfile
   already runs `python -u runpod_handler.py`).
8. Click **Deploy**. Copy the **Endpoint ID** from the endpoint page.

## 3. Test the endpoint directly

```bash
API_KEY="rpa_xxx..."
ENDPOINT_ID="abc123xyz"

# Build a tiny JSON payload with a base64-encoded test image.
python - <<'PY'
import base64, json, sys
with open("plots/example.png", "rb") as f:        # or any PNG/JPEG
    b64 = base64.b64encode(f.read()).decode()
print(json.dumps({"input": {"image_b64": b64, "diameter": 30}}))
PY > payload.json

# Submit synchronously (good for < 5 min jobs)
curl -s -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  --data @payload.json \
  "https://api.runpod.ai/v2/$ENDPOINT_ID/runsync" | jq '.output | keys'
```

A successful response looks like:

```json
{
  "status": "COMPLETED",
  "output": {
    "cell_count": 123,
    "confluency": 42.17,
    "min_intensity": 0,
    "max_intensity": 255,
    "normalized_b64": "iVBORw0KGgo...",
    "mask_b64":       "iVBORw0KGgo...",
    "histogram_b64":  "iVBORw0KGgo..."
  }
}
```

## 4. Configure the AWS Gradio box

Install only the frontend deps (no torch / cellpose / opencv needed):

```bash
pip install -r requirements-frontend.txt
```

Set the two required env vars and launch:

```bash
export RUNPOD_API_KEY="rpa_xxx..."
export RUNPOD_ENDPOINT_ID="abc123xyz"
# Optional tuning:
# export RUNPOD_POLL_TIMEOUT=300
# export RUNPOD_POLL_INTERVAL=2

python Gradio-RunPod.py
```

The UI will be on `http://<ec2-ip>:7860`. Any image uploaded by a user
will be round-tripped through the RunPod endpoint.

### Run it as a systemd service (recommended)

`/etc/systemd/system/fibroblast-gradio.service`:

```ini
[Unit]
Description=Fibroblast Gradio Frontend (RunPod backend)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/fibroblast
Environment=RUNPOD_API_KEY=rpa_xxx...
Environment=RUNPOD_ENDPOINT_ID=abc123xyz
Environment=GRADIO_SERVER_NAME=0.0.0.0
Environment=GRADIO_SERVER_PORT=7860
ExecStart=/opt/fibroblast/.venv/bin/python Gradio-RunPod.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fibroblast-gradio
```

## 5. (Optional) Persistent storage via a RunPod Network Volume

If you want every job's input + outputs kept across invocations (for audit,
reprocessing, batch export, etc.), attach a RunPod Network Volume. The
worker auto-detects it and writes artifacts without any code changes.

Steps:

1. **Create a Network Volume**
   RunPod Console -> **Storage -> Network Volumes -> New Volume**.
   Pick a datacenter and size (20 GB is plenty for thousands of jobs),
   then click Create.
   Important: the volume and the Serverless endpoint must live in the
   **same datacenter**.

2. **Attach it to the endpoint**
   Your endpoint page -> **Edit -> Advanced -> Network Volume** ->
   select the volume. Save. New workers will mount it at `/runpod-volume`
   on cold start.

   If you ever need to override that path (e.g. local testing), set
   `PERSIST_ROOT=/your/path` as an endpoint environment variable.

3. **Verify**
   Submit one test job. The response will now contain a `persist_path`
   field, e.g.:

   ```json
   {
     "cell_count": 123,
     "confluency": 41.7,
     "...": "...",
     "persist_path": "/runpod-volume/fibroblast/sync-abc-123"
   }
   ```

   The startup logs should show:
   `[startup] Persistence ENABLED at /runpod-volume/fibroblast`.

4. **Browse the files**
   From any RunPod Pod in the same datacenter, attach the volume and:

   ```bash
   ls /runpod-volume/fibroblast
   cat /runpod-volume/fibroblast/<job_id>/stats.json
   ```

On-disk layout written per job:

```
/runpod-volume/fibroblast/<job_id>/
  input.png          # the original upload
  normalized.png     # rendered preview
  mask.png           # rendered preview
  histogram.png      # rendered preview
  stats.json         # params + cell_count, confluency, min/max intensity, timestamp
```

Notes:

- If no volume is attached, the `PERSIST_ROOT` path doesn't exist and
  persistence is silently skipped. Same image, same code - just no
  `persist_path` in the response.
- `PERSIST_ROOT` and `PERSIST_SUBDIR` env vars on the endpoint let you
  change the mount path or folder name without a rebuild.
- Concurrent jobs write to *different* directories (keyed on `job["id"]`),
  so there is no locking concern.
- The network volume is NFS-backed; the tiny per-job write (~a few MB)
  is negligible compared to the inference time.

## 6. Cost + ops tips

- **Scale to zero**: set Max Workers > 0 and Idle Timeout low (e.g. 5 s).
  You are billed per active-worker-second, so idle cost is effectively $0
  between uploads.
- **First request after idle** incurs a cold start (model already baked in
  so it's usually 5-15 s on a warm GPU). Subsequent requests are much
  faster because the worker stays hot for the idle window.
- **Large images**: RunPod request bodies have a size limit (~10 MB for
  `/run`). For very large microscopy tiles, either downsample client-side
  or upload to S3 and pass a URL in the payload (worker would need a small
  change to fetch-and-decode).
- **Logs**: `RunPod Console -> your endpoint -> Workers -> Logs`.
  `print()` goes to the worker log; the `[startup]` lines confirm the
  model loaded and whether CUDA was detected.
- **Auth on the Gradio side**: the API key sits on the AWS box, never in
  the browser. Users only talk to your Gradio URL.

## 7. Updating the worker

When you change `runpod_handler.py`:

```bash
# 1. Commit and push first - the image is built from GitHub, not your disk.
git push

# 2. Build and push, tagged with the exact commit.
SHA=$(git rev-parse --short HEAD)
docker build --platform linux/amd64 -f Dockerfile.runpod \
  --build-arg REPO_REF="$SHA" -t <user>/fibroblast-runpod:"$SHA" .
docker push <user>/fibroblast-runpod:"$SHA"
```

3. In the RunPod console: endpoint -> **Edit** -> set the image to the new
   `<SHA>` tag -> **Save** -> **Release**.
4. Smoke-test with a single image before running a batch.

No change to the Gradio box is needed unless the input/output schema changes.

### Rolling back

Every previous image is still in the registry under its own SHA tag, so a bad
release is undone without rebuilding anything:

```
RunPod console -> endpoint -> Edit -> image: <user>/fibroblast-runpod:<PREVIOUS-SHA> -> Release
```

Note which SHA is live before each release so you know what to return to.
