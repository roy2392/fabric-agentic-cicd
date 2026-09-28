"""Read-only, explicitly targeted cloud discovery. Never provisions or runs jobs."""

import base64
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .contracts import ContractError


class PreflightError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PreflightError("Redirect refused; credentials remain on the configured API host")


def target_config(value):
    required = {"tenant_id", "capacity_name", "workspace_name", "ado_organization", "ado_project", "ado_repository"}
    if set(value) != required or any(not isinstance(v, str) or not v.strip() for v in value.values()):
        raise ContractError("Set exactly these nonempty fields: " + ", ".join(sorted(required)))
    try:
        uuid.UUID(value["tenant_id"])
    except ValueError as exc:
        raise ContractError("tenant_id must be a UUID") from exc
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value["ado_organization"]):
        raise ContractError("Use an Azure DevOps organization name, not a URL")
    return value


def access_token(tenant, audience):
    result = subprocess.run(["az", "account", "get-access-token", "--tenant", tenant,
                             "--resource", audience, "--output", "json"], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise PreflightError("Azure CLI authentication failed for the selected tenant; sign in explicitly and retry")
    try:
        token = json.loads(result.stdout)["accessToken"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, KeyError, IndexError) as exc:
        raise PreflightError("Could not inspect the Azure CLI token") from exc
    # Local routing sanity check only; the API validates signature and audience.
    if claims.get("tid", "").lower() != tenant.lower():
        raise PreflightError("Azure CLI returned a token for a different tenant")
    return token, {"tenant_id": claims["tid"], "object_id": claims.get("oid"),
                   "identity_kind": "delegated_user" if "scp" in claims else "application"}


class ReadClient:
    def __init__(self, base, token, opener=None, sleep=time.sleep):
        self.base = base.rstrip("/") + "/"
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.sleep = sleep

    def safe_url(self, path):
        url = urllib.parse.urljoin(self.base, path)
        parsed, base = urllib.parse.urlsplit(url), urllib.parse.urlsplit(self.base)
        decoded_path = urllib.parse.unquote(parsed.path)
        if (parsed.scheme != "https" or parsed.netloc != base.netloc or parsed.username
                or not decoded_path.startswith(base.path) or ".." in decoded_path.split("/")
                or parsed.fragment):
            raise PreflightError("Untrusted API continuation URL")
        return url

    def get(self, path):
        url = self.safe_url(path)
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if urllib.parse.urlsplit(url).hostname == "api.fabric.microsoft.com":
            headers["x-ms-fabric-skill"] = "git-integration-operations-cli"
        for attempt in range(3):
            try:
                with self.opener.open(urllib.request.Request(url, headers=headers, method="GET"), timeout=20) as response:
                    if response.status == 202:
                        raise PreflightError("Read is asynchronous; compatibility check remains incomplete")
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 503} and attempt < 2:
                    retry = exc.headers.get("Retry-After", "2")
                    self.sleep(min(10, max(0, int(retry))) if retry.isdigit() else 2)
                    continue
                # Never print response bodies or auth headers.
                raise PreflightError(f"Read-only API request failed with HTTP {exc.code}") from None
            except urllib.error.URLError:
                raise PreflightError("Read-only API could not be reached") from None

    def list_fabric(self, path):
        items, seen = [], set()
        original_url = self.safe_url(path)
        for _ in range(50):
            url = self.safe_url(path)
            if url in seen:
                raise PreflightError("Repeated continuation URL")
            seen.add(url)
            page = self.get(url)
            items.extend(page.get("value", []))
            continuation = page.get("continuationUri")
            if not continuation and page.get("continuationToken"):
                parsed = urllib.parse.urlsplit(original_url)
                query = dict(urllib.parse.parse_qsl(parsed.query))
                query["continuationToken"] = page["continuationToken"]
                continuation = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
            if not continuation:
                return items
            path = continuation
        raise PreflightError("Pagination limit reached; discovery incomplete")


def exact(items, name):
    found = [x for x in items if x.get("displayName", x.get("name")) == name]
    if len(found) != 1:
        raise PreflightError(f"Expected exactly one visible resource named {name!r}; found {len(found)}")
    return found[0]


def inspect(config):
    config = target_config(config)
    token, identity = access_token(config["tenant_id"], "https://api.fabric.microsoft.com")
    fabric = ReadClient("https://api.fabric.microsoft.com/v1/", token)
    capacity = exact(fabric.list_fabric("capacities"), config["capacity_name"])
    workspace = exact(fabric.list_fabric("workspaces"), config["workspace_name"])
    ws = str(uuid.UUID(workspace["id"]))
    connection = fabric.get(f"workspaces/{ws}/git/connection")
    items = fabric.list_fabric(f"workspaces/{ws}/items")
    ado_token, ado_identity = access_token(config["tenant_id"], "499b84ac-1321-427f-aa17-267ca6975798")
    ado = ReadClient(f"https://dev.azure.com/{config['ado_organization']}/", ado_token)
    quote = lambda v: urllib.parse.quote(v, safe="")
    repo = ado.get(f"{quote(config['ado_project'])}/_apis/git/repositories/{quote(config['ado_repository'])}?api-version=7.1")
    return {
        "evidence_kind": "read_only_discovery", "fabric_identity": identity, "ado_identity": ado_identity,
        "capacity": {k: capacity.get(k) for k in ("id", "displayName", "state", "sku")},
        "workspace": {k: workspace.get(k) for k in ("id", "displayName", "capacityId")},
        "workspace_on_selected_capacity": workspace.get("capacityId") == capacity["id"],
        "git_connection": connection.get("gitProviderDetails", {}),
        "item_types": sorted(set(x["type"] for x in items)), "repository_id": repo["id"],
        "live_execution_proven": False,
        "still_required": ["Role-scoped nonhuman identity checks", "Git credential verification", "Feature workspace permission tests",
                           "SQL connection validation", "Actual pipeline/notebook execution and data reconciliation"],
    }


def doctor():
    return {"evidence_kind": "local_tool_discovery", "tools": {name: bool(shutil.which(name)) for name in ("az", "fab", "claude", "codex")},
            "cloud_access_tested": False, "model_access_tested": False}
