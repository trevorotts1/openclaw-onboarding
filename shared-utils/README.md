# OpenClaw Shared Utilities

Common utility modules that can be imported by all OpenClaw skills.

## Available Modules

### api_key_utils.py

Unified API key detection and retrieval from multiple sources.

**Features:**
- Checks multiple env file locations in priority order
- Fuzzy name matching for common services
- Context-aware key lookup
- Security-conscious (masks keys in debug output)

**Sources checked (in order of priority):**
1. Environment variables (os.environ)
2. ~/.openclaw/.env
3. ~/clawd/secrets/.env
4. ~/.clawdbot/.env

**Usage:**

```python
from shared_utils.api_key_utils import find_api_key, get_api_key

# Find a key with fuzzy matching
openai_key = find_api_key("openai")

# Get a specific key by exact name
api_key = get_api_key("OPENAI_API_KEY")

# Find all keys for a service
aws_keys = find_all_keys_for_service("aws")
# Returns: {"AWS_ACCESS_KEY_ID": "...", "AWS_SECRET_ACCESS_KEY": "..."}

# Check if a key exists
if check_key_exists("SLACK_BOT_TOKEN"):
    print("Slack is configured")

# Find where a key is stored
source = get_key_source("OPENAI_API_KEY")
# Returns: "environment", "~/.openclaw/.env", etc.

# List all available keys (names only, for security)
available = list_all_available_keys()
```

**Supported services for fuzzy matching:**
- openai, anthropic, google, gemini
- github, slack, telegram
- stripe, twilio, sendgrid, mailgun
- notion, airtable, supabase, mongodb, redis
- aws, azure
- moonshot, kimi, minimax, deepseek
- perplexity, tavily, context7, rtrvr, kie
- n8n, ghl (GoHighLevel), convertflow, zoom
- nounproject, agentmail, toggl, linear
- asana, trello, jira, clickup

**Adding to a skill:**

1. Copy the import statement to your skill's Python script:
```python
import sys
sys.path.insert(0, '/path/to/openclaw-onboarding/shared-utils')
from api_key_utils import find_api_key, get_api_key
```

2. Or use relative imports if your skill is in the same repo:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'shared-utils'))
from api_key_utils import find_api_key
```

## Version History

**1.0.0** (March 13, 2026)
- Initial release
- API key detection from 4 sources
- Fuzzy matching for 30+ services
- Security-conscious design
