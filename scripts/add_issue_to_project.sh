#!/usr/bin/env bash

set -euo pipefail

required_vars=(
  GH_TOKEN
  REPO
  ISSUE_NUMBER
  REPO_OWNER
  PROJECT_TITLE
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "ERROR: required environment variable '$var_name' is missing."
    exit 1
  fi
done

if [[ -z "$PROJECT_OWNER" ]]; then
  PROJECT_OWNER="$REPO_OWNER"
fi

PROJECT_FIELDS_JSON="$PROJECT_FIELDS_JSON_RAW"
if [[ -z "$PROJECT_FIELDS_JSON" ]]; then
  PROJECT_FIELDS_JSON='[]'
fi

NORMALIZED_FIELD_UPDATES=$(echo "$PROJECT_FIELDS_JSON" | jq -c '
  if . == null then
    []
  elif type == "object" then
    to_entries | map({name: (.key|tostring), value: (.value|tostring)})
  elif type == "array" then
    map(
      if (type == "object" and has("name") and has("value")) then
        {name: (.name|tostring), value: (.value|tostring)}
      else
        error("Each array item must be an object with name and value")
      end
    )
  else
    error("project-fields-json must be a JSON object or array")
  end
')

edit_args=(
  issue edit "$ISSUE_NUMBER"
  --repo "$REPO"
  --add-project "$PROJECT_TITLE"
)

if [[ -n "$ISSUE_LABEL" ]]; then
  edit_args+=(--add-label "$ISSUE_LABEL")
fi

gh "${edit_args[@]}" >/dev/null

PROJECT_NUMBER=$(gh project list --owner "$PROJECT_OWNER" --format json \
  | jq -r --arg title "$PROJECT_TITLE" '.. | objects | select(.title? == $title and .number?) | .number' \
  | head -n1)

if [[ -z "$PROJECT_NUMBER" ]]; then
  echo "ERROR: project '$PROJECT_TITLE' not found under '$PROJECT_OWNER'."
  exit 1
fi

PROJECT_DATA=$(gh project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)
PROJECT_ID=$(echo "$PROJECT_DATA" | jq -r '.id // empty')

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: failed to resolve project id for '$PROJECT_TITLE'."
  exit 1
fi

PROJECT_ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --limit 200 --format json \
  | jq -r --arg repo "$REPO" --argjson issue_number "$ISSUE_NUMBER" '
      .. | objects
      | select((.content? | type) == "object")
      | select(.content.number? == $issue_number)
      | select((.content.repository? | type) != "object" or ((.content.repository.owner.login + "/" + .content.repository.name) == $repo))
      | .id // empty
    ' \
  | head -n1)

if [[ -z "$PROJECT_ITEM_ID" ]]; then
  echo "ERROR: failed to find issue #$ISSUE_NUMBER in project '$PROJECT_TITLE'."
  exit 1
fi

if [[ "$(jq 'length' <<< "$NORMALIZED_FIELD_UPDATES")" -eq 0 ]]; then
  echo "Issue #$ISSUE_NUMBER added to '$PROJECT_TITLE' under '$PROJECT_OWNER'."
  exit 0
fi

PROJECT_FIELDS=$(gh project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)

while IFS= read -r update; do
  FIELD_NAME=$(jq -r '.name' <<< "$update")
  FIELD_VALUE=$(jq -r '.value' <<< "$update")

  FIELD_ID=$(echo "$PROJECT_FIELDS" | jq -r --arg name "$FIELD_NAME" '.. | objects | select(.name? == $name and .id?) | .id' | head -n1)
  if [[ -z "$FIELD_ID" ]]; then
    echo "ERROR: project field '$FIELD_NAME' not found."
    exit 1
  fi

  OPTION_ID=$(echo "$PROJECT_FIELDS" | jq -r --arg field "$FIELD_NAME" --arg option "$FIELD_VALUE" '
      .. | objects
      | select(.name? == $field)
      | .options[]?
      | select(.name == $option)
      | .id // empty
    ' | head -n1)
  if [[ -z "$OPTION_ID" ]]; then
    echo "ERROR: option '$FIELD_VALUE' not found in field '$FIELD_NAME'."
    exit 1
  fi

  gh project item-edit \
    --id "$PROJECT_ITEM_ID" \
    --project-id "$PROJECT_ID" \
    --field-id "$FIELD_ID" \
    --single-select-option-id "$OPTION_ID" >/dev/null
done < <(jq -c '.[]' <<< "$NORMALIZED_FIELD_UPDATES")

echo "Issue #$ISSUE_NUMBER added to '$PROJECT_TITLE' under '$PROJECT_OWNER' and $(jq 'length' <<< "$NORMALIZED_FIELD_UPDATES") project field update(s) applied."