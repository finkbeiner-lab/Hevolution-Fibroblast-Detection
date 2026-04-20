#!/bin/bash
# Script to switch AWS SSO profiles

echo "Current AWS identity:"
aws sts get-caller-identity

echo ""
echo "To logout from current SSO session:"
echo "  aws sso logout"

echo ""
echo "To login with a specific SSO profile:"
echo "  aws sso login --profile <profile-name>"

echo ""
echo "Available SSO profiles (check ~/.aws/config):"
grep -A 5 "\[profile" ~/.aws/config 2>/dev/null | grep -E "\[profile|sso_start_url|sso_account_id" || echo "No SSO profiles found in config"

echo ""
echo "Common profiles might be:"
echo "  - admin (AdministratorAccess)"
echo "  - poweruser (PowerUserAccess)"
echo ""
echo "To use a specific profile:"
echo "  export AWS_PROFILE=<profile-name>"
echo "  aws sso login --profile <profile-name>"
