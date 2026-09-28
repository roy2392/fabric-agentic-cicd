"""Run Claude with a short-lived Entra token; never load the legacy API key."""
import os
from pathlib import Path
import subprocess
import sys

from fabric_agents.preflight import access_token

from scripts.settings import load


def main():
    foundry=load()['foundry']
    # Separate from the Fabric tenant's CLI profile. No account-set or key changes.
    os.environ['AZURE_CONFIG_DIR'] = os.environ.get(
        'DEMO_FOUNDRY_AZURE_CONFIG_DIR', foundry['azure_config_dir'])
    token, _ = access_token(foundry['tenant_id'], 'https://cognitiveservices.azure.com')
    env = os.environ.copy()
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_FOUNDRY_API_KEY',
                'ANTHROPIC_FOUNDRY_BASE_URL', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN'):
        env.pop(key, None)
    env.update(CLAUDE_CODE_USE_FOUNDRY='1', ANTHROPIC_FOUNDRY_RESOURCE=foundry['resource'],
               ANTHROPIC_FOUNDRY_AUTH_TOKEN=token, ANTHROPIC_MODEL=foundry['model'],
               ANTHROPIC_DEFAULT_OPUS_MODEL=foundry['model'],
               ANTHROPIC_DEFAULT_SONNET_MODEL=foundry['model'],
               ANTHROPIC_DEFAULT_HAIKU_MODEL=foundry['model'])
    return subprocess.run(['claude', *sys.argv[1:]], env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
