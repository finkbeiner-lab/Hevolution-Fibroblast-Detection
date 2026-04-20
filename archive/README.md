# Archive

Files from abandoned deployment paths, kept for reference. The active architecture is **EC2-hosted Gradio frontend → RunPod serverless inference** (see `../RUNPOD_SERVERLESS.md` and `../EC2_GRADIO_SETUP.md`).

## Contents

| Directory | What's here |
|-----------|-------------|
| `sagemaker/` | SageMaker async-inference backend — the original plan, abandoned because SageMaker is not truly serverless. Includes `Gradio-SageMaker.py`, `sagemaker_deploy.py`, deployment docs, endpoint-management scripts. |
| `aws-iam-credentials/` | IAM role / SSO / credential scripts and docs needed only when the EC2 frontend had to call SageMaker. Not needed when the backend is RunPod (no AWS credentials on EC2 except for S3 if used). |
| `docker-sagemaker/` | Dockerfile + container scripts for the SageMaker BYOC (bring-your-own-container) image. RunPod uses its own image built from `../Dockerfile.runpod`. |
| `ec2-host-fixes/` | One-off EC2 host fixes (GPG keys, security group, etc.) from initial setup. Kept as a reference if similar issues recur. |
| `stale-copies/` | macOS-style "foo copy.py" duplicates. Safe to delete. |
