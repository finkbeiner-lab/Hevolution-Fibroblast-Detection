# Deploying a change so everyone sees it

Two independent halves. **Deploy them in this order**, because the UI asks the
worker what it is at startup:

| Half | Lives on | Holds | Deployed by |
|---|---|---|---|
| **Worker** | RunPod Serverless (GPU) | `runpod_handler.py` — cellpose, confluency, the automatic diameter search | rebuilding the Docker image and repointing the endpoint |
| **UI** | EC2 (`gradio-app` systemd unit) | `Gradio-RunPod.py` — upload, controls, rendering | copying one file and restarting the service |

> The UI is a **separate process** from the worker and talks to it only over the
> RunPod REST API. It cannot import the worker, so at startup it sends a
> `{"probe": true}` job to ask which cellpose backend is running, and lays out
> its controls from the answer.
>
> If you update the UI **first**, the probe hits an old worker that does not
> understand `probe`. That is handled — the UI logs a warning and falls back to
> assuming the diameter-driven backend — but the sidebar will report
> `(unknown)` until the worker catches up. Worker first avoids it.

---

## Part 1 — the worker (RunPod)

Full context and the rollback story are in `WORKFLOW.md`; this is the short
form.

### 1. Merge to `main` and capture the commit

```bash
git push -u origin <your-branch>
gh pr create --base main --head <your-branch> --title "..." --body "..."
gh pr merge --squash
git switch main && git pull
SHA=$(git rev-parse --short HEAD) && echo "$SHA"
```

### 2. Build the image pinned to that commit

`Dockerfile.runpod` clones the repo at build time, so the image *is* the
version. Tag by SHA, never only `latest` — a SHA tag is what makes rollback a
one-click repoint instead of a rebuild.

```bash
docker build --platform linux/amd64 -f Dockerfile.runpod \
  --build-arg REPO_REF="$SHA" \
  -t <dockerhub-user>/fibroblast-runpod:"$SHA" .
docker push <dockerhub-user>/fibroblast-runpod:"$SHA"
```

`--platform linux/amd64` is not optional when you build on an Apple Silicon
Mac; RunPod hosts are x86.

### 3. Repoint the endpoint

RunPod console → your endpoint → **Edit** → image
`<dockerhub-user>/fibroblast-runpod:<SHA>` → **Save** → **Release**.

### 4. Smoke-test with one image

One job costs cents. Upload a single image and check the stats read sanely
before anyone else touches it.

---

## Part 2 — the UI (EC2)

The UI has no torch, no cellpose, and no GPU. Updating it is a file copy.

### 1. Copy the file

```bash
scp Gradio-RunPod.py ubuntu@YOUR_EC2_IP:~/fibroblast-app/
```

If `requirements-frontend.txt` changed, copy that too and reinstall:

```bash
scp requirements-frontend.txt ubuntu@YOUR_EC2_IP:~/fibroblast-app/
ssh ubuntu@YOUR_EC2_IP
cd ~/fibroblast-app && source venv/bin/activate && pip install -r requirements-frontend.txt
```

### 2. Restart the service

```bash
ssh ubuntu@YOUR_EC2_IP
sudo systemctl restart gradio-app
sudo systemctl status gradio-app
sudo journalctl -u gradio-app -f
```

### 3. Confirm the unit points at the right file

The service predates the RunPod migration, so check it once — an old unit may
still name the archived `Gradio-SageMaker.py`:

```bash
grep -E "ExecStart|Environment" /etc/systemd/system/gradio-app.service
```

`ExecStart` must end in `Gradio-RunPod.py`, and the environment must carry the
RunPod variables rather than the old SageMaker ones:

```ini
Environment="RUNPOD_API_KEY=rpa_..."
Environment="RUNPOD_ENDPOINT_ID=<endpoint-id>"
Environment="GRADIO_SERVER_NAME=0.0.0.0"
Environment="GRADIO_SERVER_PORT=7860"
ExecStart=/home/ubuntu/fibroblast-app/venv/bin/python /home/ubuntu/fibroblast-app/Gradio-RunPod.py
```

After editing the unit:

```bash
sudo systemctl daemon-reload && sudo systemctl restart gradio-app
```

### 4. Check it came up correctly

Open `http://YOUR_EC2_IP:7860` (or your nginx hostname — see
`NGINX_SETUP_GUIDE.md`) and confirm:

- the sidebar shows **Backend:** naming a real cellpose version and model, not
  `(unknown)` — `(unknown)` means the probe failed, so the worker half is not
  deployed or the API key/endpoint ID is wrong
- **Diameter mode** defaults to **Automatic** with no diameter to set
- one uploaded image returns a result, a chosen diameter, and the plot of the
  diameters it tried

---

## Verifying, and rolling back

```bash
sudo journalctl -u gradio-app -n 50        # UI errors
```

RunPod console → endpoint → **Logs** for worker errors. `[startup] Cellpose
'<version>' model '<name>' loaded` confirms which backend a worker is running.

**Rollback is repointing the endpoint at the previous SHA** — seconds, free, no
rebuild. The UI half rolls back by copying the previous `Gradio-RunPod.py` and
restarting. See `WORKFLOW.md` for the full rollback story.

---

## Two things to know before you deploy

**Automatic mode costs ~10 segmentations per image**, not one. It scans a grid
of diameters and refines around the winner. That is the price of not asking the
user for a diameter; **Single diameter** mode is one segmentation as before.
Watch the first day's GPU spend rather than assuming it looks like the old one.

**Confluency changed meaning.** Runs from before the absolute-threshold fix are
not comparable with runs after it. `stats.json` records `confluency_method` and
`backend` from now on, so the two can always be told apart — but nothing
retrofits the old runs.
