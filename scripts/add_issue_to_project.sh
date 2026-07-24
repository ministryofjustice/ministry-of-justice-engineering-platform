#!/usr/bin/env bash

set -euo pipefail

required_vars=(
  GH_TOKEN
  REPO
  ISSUE_NUMBER
  REPO_OWNER
  PROJECT_TITLE
)

# Validate the minimum inputs needed to call GitHub APIs safely.
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "ERROR: required environment variable '$var_name' is missing."
    exit 1
  fi
done

if [[ -z "$PROJECT_OWNER" ]]; then
  # If no owner is supplied, assume the project belongs to the same owner as the repo.
  PROJECT_OWNER="$REPO_OWNER"
fi

PROJECT_FIELDS_JSON="$PROJECT_FIELDS_JSON_RAW"
if [[ -z "$PROJECT_FIELDS_JSON" ]]; then
  PROJECT_FIELDS_JSON='[]'
fi

# Convert field updates into one consistent list of {name, value} entries.
# Supported input shapes:
# - {"Field":"Option"}
# - [{"name":"Field","value":"Option"}]
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

# Resolve project by number first when a numeric value is supplied; otherwise resolve by title.
if [[ "$PROJECT_TITLE" =~ ^[0-9]+$ ]]; then
  PROJECT_NUMBER="$PROJECT_TITLE"
else
  PROJECTS_JSON=$(gh project list --owner "$PROJECT_OWNER" --limit 1000 --format json)

  PROJECT_NUMBER=$(echo "$PROJECTS_JSON" | jq -r --arg title "$PROJECT_TITLE" '
    [
      .. | objects
      | select(.title? and .number?)
      | select(.title == $title)
      | .number
    ][0] // empty
  ')

  if [[ -z "$PROJECT_NUMBER" ]]; then
    # Fallback to whitespace-normalized matching to tolerate accidental spacing drift.
    PROJECT_NUMBER=$(echo "$PROJECTS_JSON" | jq -r --arg title "$PROJECT_TITLE" '
      def norm: gsub("[[:space:]]+"; " ") | gsub("^ "; "") | gsub(" $"; "");
      [
        .. | objects
        | select(.title? and .number?)
        | select((.title | norm) == ($title | norm))
        | .number
      ][0] // empty
    ')
  fi
fi

if [[ -z "$PROJECT_NUMBER" ]]; then
  echo "ERROR: project '$PROJECT_TITLE' not found under '$PROJECT_OWNER'."
  echo "INFO: Ensure the GitHub App token can read organization projects and that the title is exact."
  echo "INFO: You can also pass a numeric project number as project-title to skip title lookup."
  exit 1
fi

ISSUE_URL="https://github.com/$REPO/issues/$ISSUE_NUMBER"
PROJECT_ITEM_ID=""

# Add the issue to the project first; if that succeeds, reuse the returned item ID.
if add_item_output=$(gh project item-add "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --url "$ISSUE_URL" --format json 2>&1); then
  PROJECT_ITEM_ID=$(echo "$add_item_output" | jq -r '.id // .item.id // .data.item.id // empty')
else
  # A failure here can still be fine (for example, when the issue is already present).
  # We verify by looking up the item in the next step.
  echo "WARNING: unable to add issue to project via gh project item-add: $add_item_output"
fi

PROJECT_DATA=$(gh project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)
PROJECT_ID=$(echo "$PROJECT_DATA" | jq -r '.id // empty')

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: failed to resolve project id for '$PROJECT_TITLE'."
  exit 1
fi

if [[ -z "$PROJECT_ITEM_ID" ]]; then
  # Fallback lookup: search project items directly to find the issue's item ID.
  # Use a larger limit because this project may contain many existing items.
  PROJECT_ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --limit 1000 --format json \
    | jq -r --arg repo "$REPO" --argjson issue_number "$ISSUE_NUMBER" '
        .. | objects
        | select((.content? | type) == "object")
        | select(.content.number? == $issue_number)
        | select((.content.repository? | type) != "object" or ((.content.repository.owner.login + "/" + .content.repository.name) == $repo))
        | .id // empty
      ' \
    | head -n1)
fi

if [[ -z "$PROJECT_ITEM_ID" ]]; then
  echo "ERROR: failed to find issue #$ISSUE_NUMBER in project '$PROJECT_TITLE'."
  exit 1
fi

if [[ "$(jq 'length' <<< "$NORMALIZED_FIELD_UPDATES")" -eq 0 ]]; then
  # No field updates requested: stop after ensuring the issue is in the project.
  echo "Issue #$ISSUE_NUMBER added to '$PROJECT_TITLE' under '$PROJECT_OWNER'."
  exit 0
fi

# Retrieve project field metadata once, then reuse it for each update.
PROJECT_FIELDS=$(gh project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)

# Apply each requested single-select field value to the project item.
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

  # GitHub Projects API expects one field mutation per call.
  gh project item-edit \
    --id "$PROJECT_ITEM_ID" \
    --project-id "$PROJECT_ID" \
    --field-id "$FIELD_ID" \
    --single-select-option-id "$OPTION_ID" >/dev/null
done < <(jq -c '.[]' <<< "$NORMALIZED_FIELD_UPDATES")

echo "Issue #$ISSUE_NUMBER added to '$PROJECT_TITLE' under '$PROJECT_OWNER' and $(jq 'length' <<< "$NORMALIZED_FIELD_UPDATES") project field update(s) applied."