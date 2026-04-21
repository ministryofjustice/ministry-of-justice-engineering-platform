#!/bin/bash
# Script to find GitHub App Installation IDs
# Prerequisites: GitHub CLI (gh) must be installed and authenticated

echo "Finding GitHub App Installation IDs..."
echo ""

# For ministryofjustice organization
echo "=== ministryofjustice ==="
gh api /orgs/ministryofjustice/installation --jq '.id' 2>/dev/null || echo "Not found or no access"

echo ""

# For moj-analytical-services organization
echo "=== moj-analytical-services ==="
gh api /orgs/moj-analytical-services/installation --jq '.id' 2>/dev/null || echo "Not found or no access"

echo ""
echo "Note: This only works if you have the GitHub CLI installed and authenticated,"
echo "and if the app is already installed in these organizations."
