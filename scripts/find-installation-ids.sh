#!/bin/bash
# Script to find GitHub App Installation IDs
# Prerequisites:
# - GitHub CLI (gh) must be installed
# - gh must be authenticated with a token that can query app installations
#   (for example, a GitHub App JWT/installation-token flow for the app in scope)

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
echo "Note: This endpoint requires credentials that can read GitHub App installations."
echo "A regular user token may return 'Not found or no access' even when the app exists."
