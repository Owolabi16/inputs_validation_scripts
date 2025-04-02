#!/usr/bin/env bash

# GitHub Workflow Input Validator Script
# Validates inputs for reusable workflows

set -eo pipefail

# Function to log messages
log() {
  echo "$1"
}

error() {
  echo "::error::$1"
}

# Ensure required tools are available
if ! command -v jq &> /dev/null; then
  log "Error: jq is required but not installed"
  log "Run: apt-get update && apt-get install -y jq"
  exit 1
fi

if ! command -v yq &> /dev/null; then
  log "Installing yq for YAML processing..."
  wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/v4.25.1/yq_linux_amd64
  chmod +x /usr/local/bin/yq
fi

# Get workflow file path
WORKFLOW_PATH="${GITHUB_WORKFLOW_PATH:-".github/workflows/current.yml"}"

# Fix GitHub workflow path format
if [[ "$WORKFLOW_PATH" == *"@refs/"* ]]; then
  WORKFLOW_PATH=$(echo "$WORKFLOW_PATH" | cut -d'@' -f1)
  if [[ "$WORKFLOW_PATH" == *"/"* ]]; then
    WORKFLOW_PATH="./${WORKFLOW_PATH#*/*/}"
  fi
fi

log "Using workflow file path: $WORKFLOW_PATH"

# Function to extract inputs from a workflow file
get_workflow_inputs() {
  local file=$1
  if [ -f "$file" ]; then
    log "Attempting to read workflow file: $file"
    if command -v yq &> /dev/null; then
      yq eval '.jobs.*.with | keys' "$file" 2>/dev/null || log "No inputs found in $file"
    else
      log "yq is not available, using grep to find inputs"
      grep -A 20 "with:" "$file" | grep -v "^#" | grep ":" | cut -d ":" -f1 | tr -d ' ' || log "No inputs found in $file"
    fi
  else
    log "Workflow file not found: $file"
  fi
}

# Try to get inputs from environment variables
declare -A PROVIDED_INPUTS
log "Looking for inputs in environment variables..."
for var in $(env | grep "^INPUT_"); do
  key=$(echo "$var" | cut -d'=' -f1 | sed 's/^INPUT_//' | tr '[:upper:]' '[:lower:]')
  value=$(echo "$var" | cut -d'=' -f2-)
  PROVIDED_INPUTS["$key"]="$value"
  log "Found input from env: $key = $value"
done

# If no inputs found in environment variables, try to get from GitHub context
if [ ${#PROVIDED_INPUTS[@]} -eq 0 ]; then
  log "No inputs found in environment variables, checking GitHub context..."
  if [ -n "$GITHUB_CONTEXT" ]; then
    EVENT_TYPE=$(echo "$GITHUB_CONTEXT" | jq -r '.event_name // ""')
    log "Event type: $EVENT_TYPE"
    
    if [ "$EVENT_TYPE" = "workflow_dispatch" ]; then
      log "This is a workflow_dispatch event"
      # In a workflow_dispatch, inputs might be in the event object
      INPUTS=$(echo "$GITHUB_CONTEXT" | jq -r '.event.inputs // {}')
      if [ "$INPUTS" != "{}" ]; then
        for key in $(echo "$INPUTS" | jq -r 'keys[]'); do
          value=$(echo "$INPUTS" | jq -r ".[\"$key\"]")
          PROVIDED_INPUTS["$key"]="$value"
          log "Found input from GitHub context: $key = $value"
        done
      fi
    fi
  fi
fi

# If still no inputs, try to read from workflow files
if [ ${#PROVIDED_INPUTS[@]} -eq 0 ]; then
  log "No inputs found yet, trying to read from workflow files..."
  
  WORKFLOW_FILES=(
    "/.github/workflows/actions.yml"
    ".github/workflows/actions.yml"
    ".github/workflows/test-validator.yml"
    ".github/workflows/validator.yml"
  )
  
  for file in "${WORKFLOW_FILES[@]}"; do
    if [ -f "$file" ]; then
      log "Checking $file for inputs..."
      if command -v yq &> /dev/null; then
        # Extract "with" section from jobs using yq
        readarray -t keys < <(yq eval '.jobs.*.with | keys | .[]' "$file" 2>/dev/null || echo "")
        readarray -t values < <(yq eval '.jobs.*.with | .[]' "$file" 2>/dev/null || echo "")
        
        if [ ${#keys[@]} -gt 0 ]; then
          for i in "${!keys[@]}"; do
            key="${keys[$i]}"
            value="${values[$i]}"
            if [ -n "$key" ]; then
              PROVIDED_INPUTS["$key"]="$value"
              log "Found input from workflow file: $key = $value"
            fi
          done
          log "Successfully loaded inputs from $file"
          break
        fi
      else
        # Fallback to grep if yq is not available
        log "yq not available, using grep for basic extraction"
        readarray -t lines < <(grep -A 30 "with:" "$file" | grep -v "^#" | grep ":" | sed 's/^ *//')
        for line in "${lines[@]}"; do
          if [[ "$line" == *":"* ]]; then
            key=$(echo "$line" | cut -d ":" -f1 | tr -d ' ')
            value=$(echo "$line" | cut -d ":" -f2- | tr -d ' ')
            if [ -n "$key" ] && [ "$key" != "with" ] && [ "$key" != "secrets" ]; then
              PROVIDED_INPUTS["$key"]="$value"
              log "Found input from workflow file (grep): $key = $value"
            fi
          fi
        done
        if [ ${#PROVIDED_INPUTS[@]} -gt 0 ]; then
          log "Successfully loaded inputs from $file using grep"
          break
        fi
      fi
    fi
  done
fi

# Print all found inputs
log "Provided inputs: ${!PROVIDED_INPUTS[*]}"

# If no inputs are provided, exit early
if [ ${#PROVIDED_INPUTS[@]} -eq 0 ]; then
  log "INFO: No inputs were provided for validation."
  log "INFO: The validator will only validate inputs when inputs are available."
  log "INFO: No validation performed."
  exit 0
fi

# Print environment info
if [ -n "${PROVIDED_INPUTS[environment]}" ]; then
  log "Environment set to: ${PROVIDED_INPUTS[environment]}"
  for field in "monitor_name" "app_url" "k8_ingress_url"; do
    if [ -n "${PROVIDED_INPUTS[$field]}" ]; then
      log "$field: ${PROVIDED_INPUTS[$field]}"
    fi
  done
fi

# Validation logic
ENVIRONMENT="${PROVIDED_INPUTS[environment],,}"  # Convert to lowercase
INCONSISTENT_INPUTS=()

# Define all environment names
ALL_ENVIRONMENTS=("prod" "production" "staging" "stage" "dev" "development")

# Create array of forbidden environments based on current environment
FORBIDDEN_ENVIRONMENTS=()
for env in "${ALL_ENVIRONMENTS[@]}"; do
  if [[ ! "$env" == "$ENVIRONMENT"* ]]; then
    FORBIDDEN_ENVIRONMENTS+=("$env")
  fi
done

# Validate environment consistency
FIELDS_TO_CHECK=("monitor_name" "app_url" "k8_ingress_url")
for field in "${FIELDS_TO_CHECK[@]}"; do
  if [ -n "${PROVIDED_INPUTS[$field]}" ]; then
    FIELD_VALUE="${PROVIDED_INPUTS[$field],,}"  # Convert to lowercase
    
    # Check for forbidden environments in the field value
    for forbidden_env in "${FORBIDDEN_ENVIRONMENTS[@]}"; do
      if [[ "$FIELD_VALUE" == *"$forbidden_env"* ]]; then
        detail="contains '$forbidden_env' but environment is set to '$ENVIRONMENT'. When environment is '$ENVIRONMENT', values should not contain other environment names like ${FORBIDDEN_ENVIRONMENTS[*]}"
        INCONSISTENT_INPUTS+=("$field: $detail")
        break  # Only report one error per field
      fi
    done
    
    # Additional validation for monitor_name: no dashes or underscores
    if [ "$field" = "monitor_name" ] && [[ "$FIELD_VALUE" == *"-"* || "$FIELD_VALUE" == *"_"* ]]; then
      detail="contains dashes (-) or underscores (_), which are not allowed. Use spaces instead, like 'staging monitor report'."
      INCONSISTENT_INPUTS+=("$field: $detail")
    fi
  fi
done

# Report validation results
if [ ${#INCONSISTENT_INPUTS[@]} -gt 0 ]; then
  error "Environment consistency issues found:"
  for issue in "${INCONSISTENT_INPUTS[@]}"; do
    error "  - $issue"
  done
  
  error "Please fix these issues to ensure consistent environment naming across resources."
  error "Proper naming helps prevent accidental deployments to wrong environments."
  exit 1
else
  log "All workflow inputs are valid!"
  exit 0
fi
