#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Keep checks string-based and dependency-free so they run anywhere CI/bash is available.
assert_contains() {
  local file="$1"
  local expected="$2"

  if ! grep -Fq "$expected" "$file"; then
    echo "ERROR: Expected to find '$expected' in $file" >&2
    exit 1
  fi
}

validate_add_members_schema() {
  local file="$ROOT_DIR/.github/workflows/reusable-add-members-to-root-team.yml"

  if [[ ! -f "$file" ]]; then
    echo "ERROR: Missing workflow file: $file" >&2
    exit 1
  fi

  # Required schema for downstream callers of this reusable workflow.
  assert_contains "$file" "on:"
  assert_contains "$file" "workflow_call:"
  assert_contains "$file" "organization-name:"
  assert_contains "$file" "required: true"
  assert_contains "$file" "python-version:"
  assert_contains "$file" "default: \"3.11\""
  assert_contains "$file" "app-client-id:"
  assert_contains "$file" "app-private-key:"
  assert_contains "$file" "required: true"
}

validate_python_tests_schema() {
  local file="$ROOT_DIR/.github/workflows/reusable-python-tests.yml"

  if [[ ! -f "$file" ]]; then
    echo "ERROR: Missing workflow file: $file" >&2
    exit 1
  fi

  # Guard the public workflow_call schema to avoid silent breaking changes.
  assert_contains "$file" "on:"
  assert_contains "$file" "workflow_call:"
  assert_contains "$file" "python-version:"
  assert_contains "$file" "default: \"3.11\""
  assert_contains "$file" "run-coverage:"
  assert_contains "$file" "type: boolean"
  assert_contains "$file" "default: true"
}

validate_add_issue_to_project_schema() {
  local file="$ROOT_DIR/.github/workflows/reusable-add-issue-to-project.yml"

  if [[ ! -f "$file" ]]; then
    echo "ERROR: Missing workflow file: $file" >&2
    exit 1
  fi

  assert_contains "$file" "on:"
  assert_contains "$file" "workflow_call:"
  assert_contains "$file" "issue-number:"
  assert_contains "$file" "default: \"\""
  assert_contains "$file" "project-title:"
  assert_contains "$file" "required: true"
  assert_contains "$file" "project-owner:"
  assert_contains "$file" "default: \"\""
  assert_contains "$file" "project-fields-json:"
  assert_contains "$file" "default: \"[]\""
  assert_contains "$file" "app-id:"
  assert_contains "$file" "app-private-key:"
  assert_contains "$file" "slack-webhook-url:"
}

main() {
  # Validate each reusable workflow schema independently for clearer failures.
  validate_add_members_schema
  validate_python_tests_schema
  validate_add_issue_to_project_schema

  echo "Reusable workflow schema checks passed."
}

main "$@"
