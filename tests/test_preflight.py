import urllib.error

import pytest

from fabric_agents.contracts import ContractError
from fabric_agents.preflight import NoRedirect, PreflightError, ReadClient, exact, target_config


@pytest.mark.parametrize("url", ["https://evil.example/v1/workspaces", "http://api.fabric.microsoft.com/v1/workspaces",
                                  "https://api.fabric.microsoft.com.evil.example/v1/x", "https://api.fabric.microsoft.com/v1/../admin",
                                  "https://api.fabric.microsoft.com/v1/%2e%2e/admin", "//evil.example/v1/x"])
def test_token_cannot_follow_untrusted_urls(url):
    with pytest.raises(PreflightError):
        ReadClient("https://api.fabric.microsoft.com/v1/", "fake-token").safe_url(url)


def test_redirect_denied():
    with pytest.raises(PreflightError):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")


def test_pagination_and_loop_detection():
    client = ReadClient("https://api.fabric.microsoft.com/v1/", "fake-token")
    calls = []

    def get(url):
        calls.append(url)
        if len(calls) == 1:
            return {"value": [{"id": 1}], "continuationToken": "a+b"}
        return {"value": [{"id": 2}]}

    client.get = get
    assert len(client.list_fabric("workspaces")) == 2
    assert "continuationToken=a%2Bb" in calls[1]
    client.get = lambda url: {"value": [], "continuationUri": url}
    with pytest.raises(PreflightError, match="Repeated"):
        client.list_fabric("workspaces")


def test_ambiguous_targets_and_missing_config_rejected():
    with pytest.raises(PreflightError):
        exact([{"displayName": "Demo"}, {"displayName": "Demo"}], "Demo")
    with pytest.raises(ContractError):
        target_config({})


def test_429_retries_are_bounded_and_include_telemetry():
    class Opener:
        calls = 0

        def open(self, req, timeout):
            self.calls += 1
            assert req.get_method() == "GET"
            assert req.get_header("X-ms-fabric-skill") == "git-integration-operations-cli"
            raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {"Retry-After": "999"}, None)

    opener, delays = Opener(), []
    client = ReadClient("https://api.fabric.microsoft.com/v1/", "secret", opener=opener, sleep=delays.append)
    with pytest.raises(PreflightError, match="429") as error:
        client.get("workspaces")
    assert opener.calls == 3 and delays == [10, 10]
    assert "secret" not in str(error.value)
