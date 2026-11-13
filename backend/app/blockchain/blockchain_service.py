import json
import os
import logging
from flask import current_app, has_app_context
from web3 import Web3

logger = logging.getLogger(__name__)


class BlockchainService:
    def __init__(self):
        self.rpc_url = os.getenv("HARDHAT_RPC_URL", "http://127.0.0.1:8545")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.deployment_path = self._resolve_deployment_path()

    def _resolve_deployment_path(self) -> str:
        candidates = [
            os.getenv("DEPLOYMENT_FILE", ""),
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "..",
                    "blockchain",
                    "deployments",
                    "localhost.json",
                )
            ),
            "/app/deployments/localhost.json",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return candidates[1]

    def is_connected(self) -> bool:
        if has_app_context() and current_app.config.get("TESTING"):
            return False
        try:
            return bool(self.w3.is_connected())
        except Exception:
            return False

    def get_network_status(self) -> dict:
        connected = self.is_connected()
        if not connected:
            return {
                "connected": False,
                "rpc_url": self.rpc_url,
                "chain_id": None,
                "block_number": None,
            }
        return {
            "connected": True,
            "rpc_url": self.rpc_url,
            "chain_id": self.w3.eth.chain_id,
            "block_number": self.w3.eth.block_number,
        }

    def load_deployments(self) -> dict | None:
        if not os.path.exists(self.deployment_path):
            logger.warning("Deployment file not found at %s", self.deployment_path)
            return None
        with open(self.deployment_path, "r", encoding="utf-8") as f:
            return json.load(f)
