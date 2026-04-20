# Update Gradio App on EC2

Quick guide to update the Gradio app with the new status messages and better error handling.

## 🔄 Update Steps

### 1. Copy Updated File to EC2

From your local machine:

```bash
scp Gradio-SageMaker.py ubuntu@3.150.215.121:~/fibroblast-app/
```

### 2. Restart Gradio Service

SSH into EC2:

```bash
ssh -i your-key.pem ubuntu@3.150.215.121
```

Then restart the service:

```bash
# Check current status
sudo systemctl status gradio-app

# Restart the service
sudo systemctl restart gradio-app

# Check it started correctly
sudo systemctl status gradio-app

# View logs to verify
sudo journalctl -u gradio-app -f
```

### 3. Test the Update

1. Open browser: `http://3.150.215.121:7860`
2. Upload an image
3. Click "Run Detection"
4. **You should now see:**
   - Status messages updating in real-time:
     - "📤 Uploading image to S3..."
     - "🚀 Invoking SageMaker endpoint..."
     - "⏳ Processing... (X seconds elapsed)"
     - "✅ Complete! Processed in X seconds"
   - Progress indicator (if supported by your Gradio version)

## 🐛 If It Still Doesn't Work

### Check Service Logs

```bash
# View recent logs
sudo journalctl -u gradio-app -n 50

# Follow logs in real-time
sudo journalctl -u gradio-app -f
```

### Check for Errors

Look for:
- Import errors
- AWS credential errors
- Connection errors

### Verify File Was Updated

```bash
# Check file modification time
ls -lh ~/fibroblast-app/Gradio-SageMaker.py

# Verify it has the status_output component
grep "status_output" ~/fibroblast-app/Gradio-SageMaker.py
```

### Manual Test

If service isn't working, test manually:

```bash
cd ~/fibroblast-app
source venv/bin/activate
python Gradio-SageMaker.py
```

This will show any errors directly in the terminal.

## ✅ What Changed

The updated version now:
1. ✅ Shows real-time status messages
2. ✅ Displays progress during the 30-120 second wait
3. ✅ Better error messages
4. ✅ Logging for debugging
5. ✅ Processing time in results

## 📝 Expected Behavior

When you click "Run Detection":
1. Status immediately shows "📤 Uploading image to S3..."
2. Then "🚀 Invoking SageMaker endpoint..."
3. Then "⏳ Processing... (X seconds elapsed)" - updates every few seconds
4. Finally "✅ Complete! Processed in X seconds"
5. Results appear in the output fields

If you don't see status updates, check the browser console (F12) for JavaScript errors.
