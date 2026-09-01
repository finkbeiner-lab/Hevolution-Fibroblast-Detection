# Development workflow: branch, test free, deploy deliberately, roll back fast

## The one thing to understand first

**Pushing to GitHub does not cost money and does not deploy anything.**

Production does not watch your branch. `Dockerfile.runpod` clones the repo at
*image build* time:

```dockerfile
ARG REPO_REF=main
RUN git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /app/repo
```

So code reaches the GPU only when **you** rebuild the image and repoint the
RunPod endpoint. Those are manual steps you take on purpose.

| Action | Cost |
|---|---|
| Editing, committing, branching | free |
| Pushing to GitHub, opening a PR, CI secret scan | free |
| Running the app with `LOCAL_INFERENCE=1` | free (your hardware) |
| `docker build` / `docker push` | free (bandwidth only) |
| **A RunPod worker executing a job** | **costs GPU-seconds** |
| **An idle endpoint with min-workers > 0** | **costs money doing nothing** |

Only the last two spend money. Push as often as you like.

---

## One-time setup (already done)

```bash
git switch -c ruth/local-testing
git push -u origin ruth/local-testing
conda create -n fibroblast-local python=3.11 -y
conda activate fibroblast-local && pip install -r requirements-local.txt
```

Recommended: turn on the repo's secret scanner locally, so a stray API key is
caught before it ever leaves your machine.

```bash
pip install pre-commit && pre-commit install
```

---

## The daily loop (all free)

```bash
git switch ruth/local-testing        # 1. be on your branch
                                     # 2. edit files
conda activate fibroblast-local      # 3. test — no RunPod, no cost
./run_local.sh                       #    → http://127.0.0.1:7860

git add -p                           # 4. review each change as you stage it
git commit -m "Describe what changed and why"
git push                             # 5. safe: pushes to YOUR branch only
```

Commit often. Every commit is a restore point; small commits make rollback
surgical instead of all-or-nothing.

### Check where you are before doing anything

```bash
git status          # branch + uncommitted changes
git branch -vv      # all branches and what they track
git log --oneline -5
```

If `git status` says `On branch main`, stop and `git switch ruth/local-testing`
first. Work committed to `main` by accident is recoverable, but it's friction
you don't need.

---

## Promoting to production

Do this only when local testing looks right.

### 1. Open a pull request

```bash
git push
gh pr create --base main --head ruth/local-testing \
  --title "Add local-inference mode" --body "Tested locally with LOCAL_INFERENCE=1."
```

The gitleaks CI runs here — still free. A PR is also your written record of
what changed, which is what makes a later revert easy to reason about.

### 2. Merge, then capture the exact commit

```bash
gh pr merge --squash
git switch main && git pull
SHA=$(git rev-parse --short HEAD)
echo "$SHA"
```

### 3. Build the image pinned to that commit

Tag by SHA, **not** `latest`. A mutable `latest` tag leaves you nothing to roll
back to; a SHA tag makes rollback a one-click repoint with no rebuild.

```bash
docker build --platform linux/amd64 -f Dockerfile.runpod \
  --build-arg REPO_REF="$SHA" \
  -t <dockerhub-user>/fibroblast-runpod:"$SHA" .

docker push <dockerhub-user>/fibroblast-runpod:"$SHA"
```

Optionally also move `latest` to the same image, for convenience:

```bash
docker tag  <dockerhub-user>/fibroblast-runpod:"$SHA" <dockerhub-user>/fibroblast-runpod:latest
docker push <dockerhub-user>/fibroblast-runpod:latest
```

### 4. Point the endpoint at the new tag

RunPod console → your endpoint → **Edit** → set the image to
`<dockerhub-user>/fibroblast-runpod:<SHA>` → **Save** → **Release**.

### 5. Smoke-test with ONE image

Upload a single image through the UI and confirm the stats look sane. One job
is cents. Discovering a bug after a 500-image batch is not.

---

## Rolling back

You have two independent levers. Reach for the first one.

### Lever 1 — repoint the endpoint (seconds, free, no rebuild)

Because every image is tagged with its commit SHA, the previous image is still
sitting in the registry:

```
RunPod console → endpoint → Edit → image: <dockerhub-user>/fibroblast-runpod:<PREVIOUS-SHA> → Release
```

Production is back to the old behaviour immediately. **This is the real
rollback.** Git history is untouched, so you can debug at your leisure.

Keep a note of which SHA is currently live — the endpoint page shows it, but a
line in your lab notebook is faster.

### Lever 2 — undo the code in git

Only needed once you want the repo itself to stop carrying the bad change.

```bash
git revert <bad-sha>     # new commit that undoes it; safe on a shared branch
git push
```

`git revert` is the safe choice on anything you've already pushed — it adds a
commit rather than rewriting history, so nobody else's clone breaks.

### Undoing local work you haven't pushed

```bash
git restore <file>                  # discard uncommitted edits to one file
git restore --staged <file>         # unstage, keep the edits
git reset --soft HEAD~1             # undo last commit, KEEP the changes staged
git stash                           # park everything, retrieve with: git stash pop
```

Avoid `git reset --hard` unless you are certain — it destroys uncommitted work
with no undo.

### Recovering a branch you think you've lost

```bash
git reflog          # every HEAD position for ~90 days
git switch -c rescue <sha-from-reflog>
```

Almost nothing committed to git is truly gone. This is why committing often
matters more than committing perfectly.

---

## Keeping your branch current

If `main` moves while you're working:

```bash
git switch ruth/local-testing
git fetch origin
git merge origin/main       # or: git rebase origin/main, if you prefer linear history
```

Do this before opening a PR so conflicts surface on your machine, not in the PR.

---

## Cost discipline on RunPod

- **Set min workers to 0.** Idle workers bill continuously. With 0, you pay
  only for jobs, at the price of a cold start on the first one.
- **Test locally first.** Everything except real GPU throughput can be checked
  with `LOCAL_INFERENCE=1` for free.
- **Smoke-test with one image** before any batch.
- **Watch the idle timeout.** A long timeout keeps a worker warm — convenient
  during a session, wasteful if you walk away.

---

## Quick reference

| I want to… | Command |
|---|---|
| Start work | `git switch ruth/local-testing` |
| Test with no cost | `conda activate fibroblast-local && ./run_local.sh` |
| Save a restore point | `git add -p && git commit -m "..."` |
| Back up to GitHub | `git push` |
| See what changed | `git diff` / `git diff --staged` |
| Ship to production | PR → merge → build with `REPO_REF=<sha>` → repoint endpoint |
| **Undo production now** | Repoint endpoint to the previous SHA tag |
| Undo a pushed commit | `git revert <sha> && git push` |
| Throw away local edits | `git restore <file>` |
| Find a lost commit | `git reflog` |

See `LOCAL_TESTING.md` for the local/cluster-GPU setup, and
`RUNPOD_SERVERLESS.md` for endpoint configuration.
