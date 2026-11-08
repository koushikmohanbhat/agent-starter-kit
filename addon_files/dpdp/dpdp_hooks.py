"""DPDP add-on: hooks that connect this agent to the DPDP Data Rights Framework (catalog 5.5).

- inbound:          tokenise the customer's message before any model or framework sees it, and refuse processing
                    when the customer has withdrawn consent for this purpose (the API returns 403).
- on_session_saved: register each conversation as a lineage artifact, so an erasure request finds it.
- redact:           tokenise message content before it is written to traces (when KIT_CAPTURE_CONTENT=true).
- on_user_erased:   called after DELETE /v1/users/{id}; the framework's own certificate records the erasure.

Configure with DPDP_CONFIG (the framework's YAML) and DPDP_PURPOSE. Tools receive tokens, not raw values: a tool
that needs a real value (e.g. a delivery address) must reveal it through the framework, inside the tool.
Status: implemented against the framework's documented SDK (protect, track_artifact); not yet tested live.
"""
from __future__ import annotations

import os
from functools import lru_cache

from agent_kit.runtime import RefusedByHook

PURPOSE = os.environ.get("DPDP_PURPOSE", "customer_support")
STORE = "agent_kit_sessions"


@lru_cache(maxsize=1)
def _fw():
    try:
        from dpdp_rights.framework import DataRightsFramework  # type: ignore
    except ImportError as e:
        raise RuntimeError("the DPDP add-on needs the DPDP Data Rights Framework: "
                           "pip install git+https://github.com/koushikmohanbhat/dpdp-data-rights-framework") from e
    return DataRightsFramework.from_yaml(os.environ.get("DPDP_CONFIG", "dpdp.yaml"))


def inbound(message: str, user, session_id: str) -> str:
    fw = _fw()
    pid = fw.principal(user.id)
    try:
        with fw.context(pid, PURPOSE):
            return fw.protect(message).text            # enforces consent for PURPOSE
    except Exception as e:  # noqa: BLE001 - the framework raises its own consent error type
        if "consent" in f"{type(e).__name__} {e}".lower():
            raise RefusedByHook(f"processing for '{PURPOSE}' is not permitted for this customer (consent)") from e
        raise


def on_session_saved(session: dict, user) -> None:
    if len(session["messages"]) > 2:                    # register once, on the first turn
        return
    fw = _fw()
    with fw.context(fw.principal(user.id), PURPOSE):
        fw.track_artifact("conversation", STORE, {"session_id": session["id"], "tenant": session["tenant"]})


def redact(text: str) -> str:
    fw = _fw()
    with fw.context(fw.principal("telemetry"), PURPOSE):
        return fw.protect(text, enforce_consent=False).text


def on_user_erased(user_id: str, tenant: str) -> None:
    return None
