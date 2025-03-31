#!/usr/bin/env python3
"""
GitHub Workflow Input Validator

This script validates that all required workflow inputs are provided before the workflow gets triggered.
It specifically checks:
1. All required inputs without defaults are supplied
2. When environment is set, it ensures monitor_name, app_url, and k8_ingress_url contain the environment name in lowercase
"""

import os
import sys
import yaml
import json
from typing import Dict, List, Any, Tuple


def load_workflow_file(workflow_path: str) -> Dict[str, Any]:
    """Load and parse a GitHub workflow YAML file."""
    try:
        with open(workflow_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading workflow file: {e}")
        sys.exit(1)


def get_workflow_inputs(workflow_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract input definitions from workflow data."""
    if 'on' in workflow_data and 'workflow_call' in workflow_data['on']:
        if 'inputs' in workflow_data['on']['workflow_call']:
            return workflow_data['on']['workflow_call']['inputs']
    return {}


def get_provided_inputs() -> Dict[str, str]:
    """Get the inputs provided to the current workflow run."""
    github_context = os.environ.get('GITHUB_CONTEXT', '{}')
    try:
        context = json.loads(github_context)
        
        # For testing - UNCOMMENT THIS TO TEST WITH MOCK INPUTS
        # Always return these test inputs for validation testing
        # return {
        #     "environment": "prod",
        #     "service_name": "my-service",
        #     "monitor_name": "staging-monitor",  # This will fail environment consistency check
        #     "app_url": "https://prod.example.com",
        #     "k8_ingress_url": "prod-ingress.k8s.example.com"
        # }
        
        # For workflow_call, inputs are in event.inputs
        if 'event' in context and 'inputs' in context['event']:
            provided_inputs = context['event'].get('inputs', {})
            if provided_inputs:
                return provided_inputs
        
        # Check if this is a push event (not a workflow_call)
        event_type = context.get('event_name', '')
        if event_type == 'push':
            print("WARNING: This is a push event, not a workflow_call. No inputs to validate.")
            print("This script is designed to validate workflow_call inputs.")
            print("When used in a reusable workflow, it will validate the provided inputs.")
            print("For testing, uncomment the test inputs in the script.")
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
    Validate that when environment is set, monitor_name, app_url, and k8_ingress_url 
    contain the environment name in lowercase.
    """
    environment_lowercase = environment.lower()
    inconsistent_inputs = []
    
    fields_to_check = ['monitor_name', 'app_url', 'k8_ingress_url']
    
    for field in fields_to_check:
        if field in provided_inputs and provided_inputs[field]:
            if environment_lowercase not in provided_inputs[field].lower():
                inconsistent_inputs.append((field, f"should contain '{environment_lowercase}'"))
    
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
    
    # Get actual inputs provided to this run
    provided_inputs = get_provided_inputs()
    print(f"Provided inputs: {list(provided_inputs.keys())}")
    
    # If no inputs are provided and this isn't a workflow_call event, exit early
    if not provided_inputs:
        print("No inputs were provided for validation!")
        print("This script is meant to validate workflow_call inputs.")
        print("For testing purposes, edit the script to enable the test inputs.")
        print("Uncomment the test input section in get_provided_inputs()")
        sys.exit(0)
    
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
    
    # Report validation results
    if missing_inputs or inconsistent_inputs:
        if missing_inputs:
            print("::error::Missing required workflow inputs:")
            for input_name in missing_inputs:
                print(f"::error::  - {input_name}")
        
        if inconsistent_inputs:
            print("::error::Environment consistency issues:")
            for input_name, message in inconsistent_inputs:
                print(f"::error::  - {input_name} {message}")
        
        sys.exit(1)
    else:
        print("All workflow inputs are valid!")
        sys.exit(0)


if __name__ == "__main__":
    main()
