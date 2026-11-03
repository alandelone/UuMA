import os
import sys

sys.path.insert(0, "/home/alandelone/.local/share/uuma/engine-sources/hermes/a74e08df016459c43d9f97cb36a87cbcee5afad13c1430ac0d71c8c16ec9bfd9")
os.environ["HERMES_HOME"] = "/home/alandelone/.local/share/uuma/pilot/home"

from gateway.platforms.api_server import APIServerAdapter

adapter = APIServerAdapter(None)
print("adapter._api_key:", getattr(adapter, "_api_key", None))
print("adapter._expected_api_key():", adapter._expected_api_key())
