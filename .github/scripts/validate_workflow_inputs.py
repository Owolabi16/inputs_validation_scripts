#!/usr/bin/env python3

import os
import sys
import yaml
import json
from typing import Dict, List, Any, Tuple


def load_workflow_file(workflow_path: str) -> Dict[str, Any]:
    """Load and parse a GitHub workflow YAML file."""
    try:
        print(f"Attempting to load workflow file from: {workflow_path}")
        with open(workflow_path, 'r') as file:
            workflow_data = yaml.safe_load(file)
            print(f"Successfully loaded workflow file")
            return workflow_data
    except Exception as e:
        print(f"Error loading workflow file: {e}")
        
        # Try to load from a default location if the provided path fails
        default_paths = [
            '.github/workflows/actions.yml',
            '.github/workflows/validator.yml',
            '.github/workflows/reusable.yml'
        ]
        
        for default_path in default_paths:
            try:
                print(f"Trying to load from default path: {default_path}")
                with open(default_path, 'r') as file:
                    workflow_data = yaml.safe_load(file)
                    print(f"Successfully loaded workflow file from {default_path}")
                    return workflow_data
            except Exception as inner_e:
                print(f"Could not load from {default_path}: {inner_e}")
        
        # If we still can't load a workflow file, exit with an error
        print("Could not load any workflow file. Exiting.")
        sys.exit(1)



def get_workflow_inputs(workflow_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract input definitions from workflow data."""
    if not workflow_data:
        return {}
        
    inputs = {}
    
    # For workflow_call inputs (reusable workflows)
    if 'on' in workflow_data and 'workflow_call' in workflow_data['on']:
        if 'inputs' in workflow_data['on']['workflow_call']:
            inputs = workflow_data['on']['workflow_call']['inputs']
            print(f"Found {len(inputs)} inputs in workflow definition")
    
    return inputs


def get_provided_inputs() -> Dict[str, str]:
    """Get the inputs provided to the current workflow run."""
    github_context = os.environ.get('GITHUB_CONTEXT', '{}')
    try:
        context = json.loads(github_context)
        
        # Print event type for debugging
        print(f"Event type: {context.get('event_name', 'unknown')}")
        
        # Check for inputs from environment variables (how GitHub passes inputs to reusable workflows)
        inputs = {}
        for key, value in os.environ.items():
            if key.startswith('INPUT_'):
                input_name = key[6:].lower()  # Remove INPUT_ prefix and convert to lowercase
                inputs[input_name] = value
                print(f"Found input from env: {input_name} = {value}")
        
        if inputs:
            print(f"Found {len(inputs)} inputs from environment variables")
            return inputs
        
        # For workflow_call, inputs are in event.inputs
        if 'event' in context and 'inputs' in context['event'] and context['event']['inputs']:
            provided_inputs = context['event'].get('inputs', {})
            if provided_inputs:
                print(f"Found inputs in event.inputs: {provided_inputs}")
                return provided_inputs
        
        # Check if this is a push event (not a workflow_call)
        event_type = context.get('event_name', '')
        if event_type == 'push':
            print("WARNING: This is a push event, not a workflow_call. No inputs to validate.")
            print("This script is designed to validate workflow_call inputs.")
            print("When used in a reusable workflow, it will validate the provided inputs.")
            # Return empty dict for push events
            return {}
            
        return {}
    except json.JSONDecodeError:
        print("Error parsing GitHub context")
        return {}


def validate_required_inputs(defined_inputs: Dict[str, Dict[str, Any]], provided_inputs: Dict[str, str]) -> List[str]:
    """Validate that all required inputs without defaults are provided."""
    missing_inputs = []
    
    for input_name, input_def in defined_inputs.items():
        # Check if input is required and has no default
        is_required = input_def.get('required', False)
        has_default = 'default' in input_def
        
        # Print debug info
        print(f"Checking input: {input_name}, required: {is_required}, has_default: {has_default}")
        
        # If input is required and has no default, it must be provided
        if is_required and not has_default and (input_name not in provided_inputs or not provided_inputs[input_name]):
            missing_inputs.append(input_name)
            print(f"MISSING: {input_name}")
    
    print(f"Provided inputs: {provided_inputs.keys()}")
    print(f"Missing inputs: {missing_inputs}")
    return missing_inputs


def validate_environment_consistency(environment: str, provided_inputs: Dict[str, str]) -> List[Tuple[str, str]]:
    """
    Validate that when environment is set, the values of monitor_name, app_url, and k8_ingress_url 
    do not contain other environment names (staging/prod/dev).
    Also validates that monitor_name doesn't have dashes or underscores.
    """
    environment_lowercase = environment.lower()
    inconsistent_inputs = []
    
    # Define all environment names
    all_environments = ["prod", "production", "staging", "stage", "dev", "development"]
    
    # Remove the current environment from the list of forbidden environments
    forbidden_environments = [env for env in all_environments if not env.startswith(environment_lowercase)]
    
    fields_to_check = ['monitor_name', 'app_url', 'k8_ingress_url']
    
    for field in fields_to_check:
        if field in provided_inputs and provided_inputs[field]:
            field_value = provided_inputs[field].lower()
            
            # Check for forbidden environments in the field value
            for forbidden_env in forbidden_environments:
                if forbidden_env in field_value:
                    detail = f"contains '{forbidden_env}' but environment is set to '{environment_lowercase}'. " \
                             f"When environment is '{environment_lowercase}', values should not contain " \
                             f"other environment names like {', '.join(forbidden_environments)}."
                    inconsistent_inputs.append((field, detail))
                    break  # Only report one error per field
            
            # Additional validation for monitor_name: no dashes or underscores
            if field == 'monitor_name' and ('-' in field_value or '_' in field_value):
                detail = "contains dashes (-) or underscores (_), which are not allowed. " \
                         "Use spaces instead, like 'staging monitor report'."
                inconsistent_inputs.append((field, detail))
    
    return inconsistent_inputs


def main():
    """Main entry point for the script."""
    # Get the workflow file path from environment or use default
    workflow_file = os.environ.get('GITHUB_WORKFLOW_PATH', '.github/workflows/current.yml')
    
    # Fix GitHub workflow path format (remove repository and ref information)
    if '@refs/' in workflow_file:
        # Extract just the workflow file path
        workflow_file = workflow_file.split('@refs/')[0]
        # Remove repository name from the beginning
        if '/' in workflow_file:
            workflow_file = './' + '/'.join(workflow_file.split('/')[2:])
    
    print(f"Using workflow file path: {workflow_file}")
    
    # Load workflow definition
    workflow_data = load_workflow_file(workflow_file)
    
    # Get defined inputs from workflow file
    defined_inputs = get_workflow_inputs(workflow_data)
    print(f"Defined inputs: {list(defined_inputs.keys())}")
    
    # Print all environment variables with INPUT_ prefix for debugging
    print("Environment variables with INPUT_ prefix:")
    for key, value in os.environ.items():
        if key.startswith('INPUT_'):
            print(f"  {key} = {value}")
    
    # Get actual inputs provided to this run
    provided_inputs = get_provided_inputs()
    print(f"Provided inputs: {list(provided_inputs.keys())}")
    
    # If no inputs are provided and this isn't a workflow_call event, exit early
    github_context = os.environ.get('GITHUB_CONTEXT', '{}')
    try:
        context = json.loads(github_context)
        event_type = context.get('event_name', '')
        if event_type != 'workflow_call' and not provided_inputs:
            print("INFO: This is not being run as a workflow_call event.")
            print("INFO: The validator will only validate inputs when called via workflow_call.")
            print("INFO: No validation performed during push events.")
            # Exit successfully since there's nothing to validate in a push event
            sys.exit(0)
    except:
        pass
    
    # Print debugging information about environment
    if 'environment' in provided_inputs:
        print(f"Environment set to: {provided_inputs['environment']}")
        for field in ['monitor_name', 'app_url', 'k8_ingress_url']:
            if field in provided_inputs:
                print(f"{field}: {provided_inputs[field]}")
    
    # Validate required inputs
    missing_inputs = validate_required_inputs(defined_inputs, provided_inputs)
    
    # Validate environment consistency if environment is provided
    inconsistent_inputs = []
    if 'environment' in provided_inputs and provided_inputs['environment']:
        inconsistent_inputs = validate_environment_consistency(
            provided_inputs['environment'], 
            provided_inputs
        )
    
    # Report validation results with more detailed messages
    if missing_inputs or inconsistent_inputs:
        if missing_inputs:
            print("::error::Missing required workflow inputs:")
            for input_name in missing_inputs:
                print(f"::error::  - {input_name}: This input is required but was not provided.")
                print(f"    Please add '{input_name}' to your workflow call.")
        
        if inconsistent_inputs:
            print("::error::Environment consistency issues found:")
            for input_name, message in inconsistent_inputs:
                print(f"::error::  - {input_name}: {message}")
                
        print("\n::error::Please fix these issues to ensure consistent environment naming across resources.")
        print("::error::Proper naming helps prevent accidental deployments to wrong environments.")
        sys.exit(1)
    else:
        print("All workflow inputs are valid!")
        sys.exit(0)


if __name__ == "__main__":
    main()
