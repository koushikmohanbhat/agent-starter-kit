import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "kits" / "support-agent"


@pytest.fixture
def kit(tmp_path, monkeypatch):
    d = tmp_path / "kit"
    shutil.copytree(KIT, d, ignore=shutil.ignore_patterns("__pycache__", ".kit"))
    for k in [k for k in os.environ if k.startswith(("KIT_", "MODEL_", "AGENT_FRAMEWORK", "ORDER_API", "SESSION_STORE", "REFUND_"))]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SESSION_STORE", "memory://")
    return d
