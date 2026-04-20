#!/bin/bash
# Script to check SageMaker endpoint CloudWatch logs

ENDPOINT_NAME="${1:-fibroblast-detection-endpoint}"
REGION="${2:-us-east-2}"

echo "Checking logs for endpoint: $ENDPOINT_NAME"
echo "Region: $REGION"
echo ""

# Check if endpoint exists
aws sagemaker describe-endpoint --endpoint-name "$ENDPOINT_NAME" --region "$REGION" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ Endpoint '$ENDPOINT_NAME' not found"
    exit 1
fi

# Get endpoint status
STATUS=$(aws sagemaker describe-endpoint --endpoint-name "$ENDPOINT_NAME" --region "$REGION" --query 'EndpointStatus' --output text)
echo "Endpoint Status: $STATUS"
echo ""

if [ "$STATUS" == "Failed" ]; then
    FAILURE_REASON=$(aws sagemaker describe-endpoint --endpoint-name "$ENDPOINT_NAME" --region "$REGION" --query 'FailureReason' --output text)
    echo "❌ Failure Reason: $FAILURE_REASON"
    echo ""
fi

# Check CloudWatch logs
LOG_GROUP="/aws/sagemaker/Endpoints/$ENDPOINT_NAME"
echo "CloudWatch Log Group: $LOG_GROUP"
echo ""

# Try to get recent logs
echo "Recent logs (last 100 lines):"
aws logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" \
    --start-time $(($(date +%s) - 3600))000 \
    --query 'events[*].message' \
    --output text 2>/dev/null | tail -100 || \
    echo "No logs found or log group doesn't exist yet. Try:"
    echo "  aws logs describe-log-streams --log-group-name $LOG_GROUP --region $REGION"
echo ""

echo "To view logs in real-time:"
echo "  aws logs tail $LOG_GROUP --region $REGION --follow"
echo ""
echo "Or view in AWS Console:"
echo "  https://console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/$LOG_GROUP"
