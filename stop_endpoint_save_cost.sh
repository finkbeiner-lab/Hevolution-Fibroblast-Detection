#!/bin/bash
# Stop SageMaker endpoint to avoid charges when not in use

set -e
ENDPOINT_NAME="fibroblast-detection-endpoint"
REGION="us-east-2"

echo "=========================================="
echo "Stop SageMaker Endpoint (Stop Charges)"
echo "=========================================="
echo ""
echo "Endpoint: $ENDPOINT_NAME"
echo "Region:   $REGION"
echo ""
echo "After deletion:"
echo "  - You will NOT be charged for this endpoint"
echo "  - To use the app again, run: python sagemaker_deploy.py --skip-ecr --image-uri 098023138344.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest"
echo ""
read -p "Continue and delete the endpoint? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Deleting endpoint..."
aws sagemaker delete-endpoint --endpoint-name "$ENDPOINT_NAME" --region "$REGION" && echo "✅ Endpoint deletion initiated" || echo "⚠️  Endpoint may not exist or already deleted"

echo ""
echo "Waiting 2 minutes for endpoint to be removed (required before deleting config)..."
sleep 120

echo ""
echo "Deleting endpoint config..."
aws sagemaker delete-endpoint-config --endpoint-config-name "$ENDPOINT_NAME" --region "$REGION" && echo "✅ Endpoint config deleted" || echo "⚠️  Config may not exist or still in use (try again in a few minutes)"

echo ""
echo "=========================================="
echo "✅ Done. You are no longer charged for this endpoint."
echo "=========================================="
echo ""
echo "To deploy again when needed:"
echo "  aws sso login --profile admin"
echo "  python sagemaker_deploy.py --skip-ecr --image-uri 098023138344.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest"
echo ""
