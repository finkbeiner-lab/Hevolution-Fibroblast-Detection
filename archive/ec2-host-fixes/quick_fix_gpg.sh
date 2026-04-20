#!/bin/bash
# Quick fix for Google Cloud SDK GPG key issue

echo "Fixing Google Cloud SDK GPG key issue..."

# Method 1: Add the key properly
echo "Method 1: Adding GPG key..."
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    sudo apt-key add - 2>/dev/null && echo "✅ Key added via apt-key" || echo "⚠️ apt-key method failed"

# Method 2: Try with gpg --dearmor
echo ""
echo "Method 2: Adding key to keyring..."
mkdir -p /tmp/gpg-fix
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg -o /tmp/gpg-fix/cloud.gpg 2>/dev/null
if [ -f /tmp/gpg-fix/cloud.gpg ]; then
    sudo gpg --dearmor /tmp/gpg-fix/cloud.gpg -o /usr/share/keyrings/cloud.google.gpg 2>/dev/null && \
        echo "✅ Key added to keyring" || echo "⚠️ Keyring method failed"
    rm -rf /tmp/gpg-fix
fi

# Method 3: Temporarily disable the repo if methods above fail
echo ""
read -p "If errors persist, disable Google Cloud SDK repo temporarily? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Disabling Google Cloud SDK repository..."
    sudo find /etc/apt/sources.list.d/ -name "*cloud*" -o -name "*google*" | \
        xargs -I {} sudo sed -i 's|^deb|#deb|g' {} 2>/dev/null || true
    echo "✅ Repository disabled"
fi

# Try updating
echo ""
echo "Testing apt-get update..."
if sudo apt-get update 2>&1 | grep -q "NO_PUBKEY C0BA5CE6DC6315A3"; then
    echo "⚠️  Issue persists, but this won't block NVIDIA installation"
    echo "   The installation script will handle this automatically"
else
    echo "✅ GPG issue resolved!"
fi
