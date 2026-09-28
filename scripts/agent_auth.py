"""Short-lived application tokens with a role-specific local certificate."""
import base64
import json
from pathlib import Path
import time
import uuid
import urllib.parse
import urllib.request
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fabric_agents.preflight import NoRedirect

ROOT = Path(__file__).resolve().parents[1]


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def token_for(role, audience):
    if role not in ('developer', 'reviewer'):
        raise ValueError('Unknown role')
    allowed = {'499b84ac-1321-427f-aa17-267ca6975798'}
    if role == 'developer':
        allowed |= {'https://api.fabric.microsoft.com', 'https://storage.azure.com'}
    if audience not in allowed:
        raise ValueError('Audience outside role scope')
    m = json.loads((ROOT / 'config/live-resources.json').read_text())
    directory = ROOT / '.runs/identities' / role
    cert = x509.load_pem_x509_certificate((directory / 'public.pem').read_bytes())
    key = serialization.load_pem_private_key((directory / 'private.key').read_bytes(), None)
    url = f"https://login.microsoftonline.com/{m['tenant_id']}/oauth2/v2.0/token"
    now = int(time.time())
    claims = {'aud': url, 'iss': m['agents'][role]['app_id'],
              'sub': m['agents'][role]['app_id'], 'jti': str(uuid.uuid4()),
              'nbf': now - 30, 'exp': now + 300}
    header = {'alg': 'RS256', 'typ': 'JWT', 'x5t': b64(cert.fingerprint(hashes.SHA1()))}
    body = b64(json.dumps(header).encode()) + '.' + b64(json.dumps(claims).encode())
    assertion = body + '.' + b64(key.sign(body.encode(), padding.PKCS1v15(), hashes.SHA256()))
    data = urllib.parse.urlencode({'client_id': claims['iss'], 'scope': audience.rstrip('/') + '/.default',
        'grant_type': 'client_credentials', 'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
        'client_assertion': assertion}).encode()
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url, data=data), timeout=30) as r:
        result = json.load(r)
    token = result['access_token']
    payload = token.split('.')[1]
    decoded = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    if decoded.get('tid') != m['tenant_id'] or decoded.get('oid') != m['agents'][role]['object_id']:
        raise RuntimeError('Unexpected application identity')
    return token
