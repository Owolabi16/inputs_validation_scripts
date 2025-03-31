#!/usr/bin/env python3
"""
GitHub Workflow Input Validator

This script validates that all required workflow inputs are provided before the workflow gets triggered.
It reads the workflow definition and checks against the provided inputs.

Usage:
  - Add this as a step in your GitHub Actions workflow
  - Configure the required inputs for each workflow type
"""

import os
import sys
import yaml
import json
from typing import Dict, List, Set, Optional, Any


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
    inputs = {}
    
    # For workflow_call inputs (reusable workflows)
    if 'on' in workflow_data and 'workflow_call' in workflow_data['on']:
        if 'inputs' in workflow_data['on']['workflow_call']:
            inputs = workflow_data['on']['workflow_call']['inputs']
    
    return inputs


def get_provided_inputs() -> Dict[str, str]:
    """Get the inputs provided to the current workflow run."""
    github_context = os.environ.get('GITHUB_CONTEXT', '{}')
    try:
        context = json.loads(github_context)
        # For workflow_call, inputs are in event.inputs
        if 'event' in context and 'inputs' in context['event']:
            return context['event']['inputs']
        return {}
    except json.JSONDecodeError:
        print("Error parsing GitHub context")
        return {}


def get_workflow_type(workflow_data: Dict[str, Any]) -> Optional[str]:
    """Determine the type of workflow based on its structure or metadata."""
    if 'name' in workflow_data:
        workflow_name = workflow_data['name'].lower()
        if 'deploy' in workflow_name:
            return 'deployment'
        elif 'build' in workflow_name:
            return 'build'
        elif 'test' in workflow_name:
            return 'test'
    
    # You can add more sophisticated detection logic here
    return None


def get_required_inputs_for_type(workflow_type: str, selected_options: Dict[str, str]) -> Set[str]:
    """Get the list of required inputs based on workflow type and selected options."""
    # This is where you define your validation rules
    required_inputs = set()
    
    if workflow_type == 'deployment':
        # Basic required inputs for all deployment workflows
        required_inputs = {'environment', 'version', 'approval_required'}
        
        # Add additional required inputs based on environment
        if selected_options.get('environment') == 'production':
            required_inputs.update({'approval_ticket', 'rollback_plan'})
        
        # Add additional inputs based on service type if that's a selection
        if 'service_type' in selected_options:
            if selected_options['service_type'] == 'database':
                required_inputs.update({'backup_strategy', 'downtime_window'})
            elif selected_options['service_type'] == 'api':
                required_inputs.update({'api_version', 'documentation_url'})
    
    elif workflow_type == 'build':
        required_inputs = {'repository', 'branch', 'build_type'}
        
        # Different build types might need different inputs
        if 'build_type' in selected_options:
            if selected_options['build_type'] == 'docker':
                required_inputs.update({'docker_registry', 'docker_tag'})
            elif selected_options['build_type'] == 'npm':
                required_inputs.add('npm_token')
    
    elif workflow_type == 'test':
        required_inputs = {'test_suite', 'environment'}
        
        # Different test suites might need different inputs
        if 'test_suite' in selected_options:
            if selected_options['test_suite'] == 'integration':
                required_inputs.update({'api_key', 'test_data_path'})
            elif selected_options['test_suite'] == 'performance':
                required_inputs.update({'load_level', 'duration'})
    
    return required_inputs


def validate_workflow_inputs(workflow_path: str) -> List[str]:
    """
    Validate that all required inputs for the workflow are provided.
    Returns a list of missing required inputs.
    """
    # Load workflow definition
    workflow_data = load_workflow_file(workflow_path)
    
    # Get defined inputs from workflow file
    defined_inputs = get_workflow_inputs(workflow_data)
    
    # Get actual inputs provided to this run
    provided_inputs = get_provided_inputs()
    
    # Determine workflow type
    workflow_type = get_workflow_type(workflow_data)
    if not workflow_type:
        print("Warning: Could not determine workflow type. Using basic validation.")
        # Fall back to basic validation - just check if required inputs are provided
        missing_inputs = []
        for input_name, input_def in defined_inputs.items():
            if input_def.get('required', False) and input_name not in provided_inputs:
                missing_inputs.append(input_name)
        return missing_inputs
    
    # Get required inputs based on workflow type and selected options
    required_inputs = get_required_inputs_for_type(workflow_type, provided_inputs)
    
    # Check for missing inputs
    missing_inputs = []
    for input_name in required_inputs:
        if input_name not in provided_inputs or not provided_inputs[input_name]:
            missing_inputs.append(input_name)
    
    return missing_inputs


def main():
    """Main entry point for the script."""
    # Get the workflow file path from environment or use default
    workflow_file = os.environ.get('GITHUB_WORKFLOW_PATH', '.github/workflows/current.yml')
    
    # Validate workflow inputs
    missing_inputs = validate_workflow_inputs(workflow_file)
    
    if missing_inputs:
        print("::error::Missing required workflow inputs:")
        for input_name in missing_inputs:
            print(f"::error::  - {input_name}")
        sys.exit(1)
    else:
        print("All required workflow inputs are provided!")
        sys.exit(0)


if __name__ == "__main__":
    main()
