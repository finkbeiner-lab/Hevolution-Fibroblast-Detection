#!/bin/bash
# Quick fix for GPG key issues blocking apt-get update

echo "=========================================="
echo "Fixing GPG Key Issues"
echo "=========================================="
echo ""

# Fix Google Cloud SDK GPG key
echo "🔧 Fixing Google Cloud SDK GPG key..."
if curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg 2>/dev/null; then
    echo "✅ Google Cloud SDK key added"
else
    echo "⚠️  Could not add Google Cloud SDK key (may not be needed)"
fi

# Alternative: Remove the problematic repo if not needed
echo ""
read -p "Do you use Google Cloud SDK? If not, we can disable this repo (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Disabling Google Cloud SDK repository..."
    sudo sed -i 's|deb https://packages.cloud.google.com/apt cloud-sdk|#deb https://packages.cloud.google.com/apt cloud-sdk|' /etc/apt/sources.list.d/*.list 2>/dev/null || true
    echo "✅ Repository disabled"
fi

# Try updating again
echo ""
echo "🔄 Updating package lists..."
if sudo apt-get update 2>&1 | tee /tmp/apt-update.log; then
    echo ""
    echo "✅ Package lists updated successfully"
    rm -f /tmp/apt-update.log
else
    echo ""
    if grep -q "NO_PUBKEY C0BA5CE6DC6315A3" /tmp/apt-update.log; then
        echo "⚠️  Google Cloud SDK repo still has issues (non-critical)"
        echo "   This won't block NVIDIA Container Toolkit installation"
    else
        echo "❌ Other errors found. Check the output above."
    fi
    rm -f /tmp/apt-update.log
fi
