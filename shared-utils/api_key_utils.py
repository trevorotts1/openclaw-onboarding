#!/usr/bin/env python3
"""
OpenClaw Shared Utilities - API Key Detection Module

This module provides a unified way to detect and retrieve API keys
from various sources across the OpenClaw ecosystem.

Usage:
    from api_key_utils import find_api_key, get_api_key
    
    # Find a key with fuzzy matching
    key = find_api_key("openai")
    
    # Get a specific key by name
    key = get_api_key("OPENAI_API_KEY")

Sources checked (in order of priority):
    1. Environment variables (os.environ)
    2. ~/.openclaw/.env
    3. ~/clawd/secrets/.env
    4. ~/.clawdbot/.env

Author: OpenClaw
Version: 1.0.0
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Priority order for env file locations
ENV_FILE_PATHS = [
    "~/.openclaw/.env",
    "~/clawd/secrets/.env",
    "~/.clawdbot/.env",
]

# Common API key name patterns for fuzzy matching
KEY_PATTERNS = {
    "openai": ["OPENAI_API_KEY", "OPENAI_KEY", "OPEN_AI_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GCP_API_KEY", "GOOGLE_CLOUD_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"],
    "github": ["GITHUB_TOKEN", "GITHUB_API_TOKEN", "GH_TOKEN"],
    "slack": ["SLACK_BOT_TOKEN", "SLACK_TOKEN", "SLACK_API_TOKEN"],
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN"],
    "stripe": ["STRIPE_API_KEY", "STRIPE_KEY", "STRIPE_SECRET_KEY"],
    "twilio": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY"],
    "sendgrid": ["SENDGRID_API_KEY", "SENDGRID_KEY"],
    "mailgun": ["MAILGUN_API_KEY", "MAILGUN_KEY"],
    "notion": ["NOTION_TOKEN", "NOTION_API_KEY", "NOTION_INTEGRATION_TOKEN"],
    "airtable": ["AIRTABLE_API_KEY", "AIRTABLE_KEY", "AIRTABLE_TOKEN"],
    "supabase": ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_KEY"],
    "mongodb": ["MONGODB_URI", "MONGO_URI", "MONGODB_URL"],
    "redis": ["REDIS_URL", "REDIS_URI", "REDIS_HOST"],
    "aws": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    "azure": ["AZURE_API_KEY", "AZURE_KEY", "AZURE_OPENAI_KEY"],
    "moonshot": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    "minimax": ["MINIMAX_API_KEY", "MINIMAX_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY", "DEEPSEEK_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY", "PERPLEXITY_KEY"],
    "tavily": ["TAVILY_API_KEY", "TAVILY_KEY"],
    "context7": ["CONTEXT7_API_KEY", "CONTEXT7_KEY"],
    "rtrvr": ["RTRVR_API_KEY", "RTRVR_KEY"],
    "kie": ["KIE_API_KEY", "KIE_KEY"],
    "n8n": ["N8N_API_KEY", "N8N_WEBHOOK_KEY"],
    "ghl": ["GOHIGHLEVEL_API_KEY", "GHL_API_KEY", "GOHIGHLEVEL_KEY"],
    "convertflow": ["CONVERTFLOW_API_KEY", "CF_API_KEY"],
    "zoom": ["ZOOM_API_KEY", "ZOOM_JWT_TOKEN"],
    "nounproject": ["NOUN_PROJECT_API_KEY", "NOUNPROJECT_API_KEY"],
    "agentmail": ["AGENTMAIL_API_KEY", "AGENT_MAIL_KEY"],
    "toggl": ["TOGGL_API_TOKEN", "TOGGL_TRACK_TOKEN"],
    "linear": ["LINEAR_API_KEY", "LINEAR_TOKEN"],
    "asana": ["ASANA_TOKEN", "ASANA_API_KEY"],
    "trello": ["TRELLO_API_KEY", "TRELLO_TOKEN"],
    "jira": ["JIRA_API_TOKEN", "JIRA_TOKEN"],
    "clickup": ["CLICKUP_API_KEY", "CLICKUP_TOKEN"],
}


def _expand_path(path: str) -> Path:
    """Expand user home directory in path."""
    return Path(os.path.expanduser(path))


def _parse_env_file(filepath: Path) -> Dict[str, str]:
    """
    Parse an .env file and return a dictionary of key-value pairs.
    
    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - Quoted values
    - export KEY=VALUE syntax
    """
    env_vars = {}
    
    if not filepath.exists():
        return env_vars
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Handle export KEY=VALUE syntax
                if line.startswith('export '):
                    line = line[7:]
                
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    env_vars[key] = value
    except Exception as e:
        # Silently fail - file might not exist or be readable
        pass
    
    return env_vars


def _load_all_env_files() -> Dict[str, str]:
    """
    Load all env files in priority order.
    Later files override earlier ones.
    """
    all_vars = {}
    
    for path in ENV_FILE_PATHS:
        filepath = _expand_path(path)
        env_vars = _parse_env_file(filepath)
        all_vars.update(env_vars)
    
    return all_vars


def _fuzzy_match_key(search_term: str) -> List[str]:
    """
    Find potential key names matching the search term.
    Returns a list of candidate key names in priority order.
    """
    search_lower = search_term.lower().replace('_', '').replace('-', '')
    candidates = []
    
    # Direct lookup in patterns
    if search_lower in KEY_PATTERNS:
        candidates.extend(KEY_PATTERNS[search_lower])
    
    # Partial matches in patterns
    for pattern_name, keys in KEY_PATTERNS.items():
        if search_lower in pattern_name or pattern_name in search_lower:
            candidates.extend(keys)
    
    # Generate common variations
    variations = [
        f"{search_term.upper()}_API_KEY",
        f"{search_term.upper()}_KEY",
        f"{search_term.upper()}_TOKEN",
        f"{search_term.upper()}_SECRET",
        search_term.upper(),
    ]
    candidates.extend(variations)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)
    
    return unique_candidates


def get_api_key(key_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a specific API key by its exact name.
    
    Checks sources in this order:
        1. Environment variables
        2. ~/.openclaw/.env
        3. ~/clawd/secrets/.env
        4. ~/.clawdbot/.env
    
    Args:
        key_name: The exact name of the environment variable
        default: Default value if key not found
    
    Returns:
        The API key value or default if not found
    
    Example:
        >>> get_api_key("OPENAI_API_KEY")
        "sk-..."
    """
    # Check environment variables first
    if key_name in os.environ:
        return os.environ[key_name]
    
    # Check env files
    env_vars = _load_all_env_files()
    if key_name in env_vars:
        return env_vars[key_name]
    
    return default


def find_api_key(service_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Find an API key using fuzzy matching on service name.
    
    This is useful when you don't know the exact environment variable name.
    It tries common naming patterns and variations.
    
    Args:
        service_name: The service name (e.g., "openai", "slack", "stripe")
        default: Default value if no key found
    
    Returns:
        The API key value or default if not found
    
    Example:
        >>> find_api_key("openai")
        "sk-..."
        >>> find_api_key("anthropic")
        "sk-ant-..."
    """
    # Get candidate key names
    candidates = _fuzzy_match_key(service_name)
    
    # Check environment variables first
    for candidate in candidates:
        if candidate in os.environ:
            return os.environ[candidate]
    
    # Check env files
    env_vars = _load_all_env_files()
    for candidate in candidates:
        if candidate in env_vars:
            return env_vars[candidate]
    
    return default


def find_all_keys_for_service(service_name: str) -> Dict[str, str]:
    """
    Find all API keys related to a service.
    
    Returns a dictionary of key names to values.
    Useful when a service has multiple keys (e.g., AWS has access key + secret).
    
    Args:
        service_name: The service name to search for
    
    Returns:
        Dictionary of {key_name: key_value} for all matching keys
    
    Example:
        >>> find_all_keys_for_service("aws")
        {"AWS_ACCESS_KEY_ID": "AKIA...", "AWS_SECRET_ACCESS_KEY": "..."}
    """
    results = {}
    search_lower = service_name.lower()
    
    # Get all possible sources
    all_vars = dict(os.environ)
    all_vars.update(_load_all_env_files())
    
    # Find keys matching the service name
    for key, value in all_vars.items():
        key_lower = key.lower()
        if search_lower in key_lower:
            results[key] = value
    
    return results


def check_key_exists(key_name: str) -> bool:
    """
    Check if a specific API key exists in any source.
    
    Args:
        key_name: The exact name of the environment variable
    
    Returns:
        True if the key exists, False otherwise
    
    Example:
        >>> check_key_exists("OPENAI_API_KEY")
        True
    """
    return get_api_key(key_name) is not None


def get_key_source(key_name: str) -> Optional[str]:
    """
    Find where a specific key is stored.
    
    Args:
        key_name: The exact name of the environment variable
    
    Returns:
        String indicating the source: "environment", "~/.openclaw/.env",
        "~/clawd/secrets/.env", "~/.clawdbot/.env", or None if not found
    
    Example:
        >>> get_key_source("OPENAI_API_KEY")
        "environment"
    """
    # Check environment first
    if key_name in os.environ:
        return "environment"
    
    # Check each env file
    for path in ENV_FILE_PATHS:
        filepath = _expand_path(path)
        env_vars = _parse_env_file(filepath)
        if key_name in env_vars:
            return path
    
    return None


def list_all_available_keys() -> List[str]:
    """
    List all available API keys across all sources.
    
    Returns a list of key names (not values - for security).
    
    Returns:
        List of key names that are available
    
    Example:
        >>> list_all_available_keys()
        ["OPENAI_API_KEY", "SLACK_BOT_TOKEN", "GITHUB_TOKEN"]
    """
    all_keys = set()
    
    # Add environment variables
    for key in os.environ:
        # Filter out common non-API keys
        if any(term in key.upper() for term in ['API', 'KEY', 'TOKEN', 'SECRET', 'AUTH']):
            all_keys.add(key)
    
    # Add keys from env files
    env_vars = _load_all_env_files()
    for key in env_vars:
        if any(term in key.upper() for term in ['API', 'KEY', 'TOKEN', 'SECRET', 'AUTH']):
            all_keys.add(key)
    
    return sorted(list(all_keys))


# Convenience aliases for common services
def get_openai_key() -> Optional[str]:
    """Get OpenAI API key."""
    return find_api_key("openai")


def get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key."""
    return find_api_key("anthropic")


def get_google_key() -> Optional[str]:
    """Get Google API key."""
    return find_api_key("google")


def get_github_token() -> Optional[str]:
    """Get GitHub token."""
    return find_api_key("github")


def get_slack_token() -> Optional[str]:
    """Get Slack token."""
    return find_api_key("slack")


def get_stripe_key() -> Optional[str]:
    """Get Stripe API key."""
    return find_api_key("stripe")


if __name__ == "__main__":
    # Demo/test mode
    print("OpenClaw API Key Utils - Test Mode")
    print("=" * 50)
    
    # List all available keys
    available = list_all_available_keys()
    print(f"\nFound {len(available)} potential API keys:")
    for key in available[:20]:  # Limit output
        source = get_key_source(key)
        print(f"  • {key} (from {source})")
    
    if len(available) > 20:
        print(f"  ... and {len(available) - 20} more")
    
    # Test fuzzy matching
    print("\n" + "=" * 50)
    print("Testing fuzzy matching:")
    test_services = ["openai", "slack", "stripe"]
    for service in test_services:
        key = find_api_key(service)
        if key:
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            print(f"  • {service}: Found ({masked})")
        else:
            print(f"  • {service}: Not found")
