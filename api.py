"""
MemeMiningBot API client.
Handles all HTTP communication with meme-mining.xyz API.
"""
import requests
import json
import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

BASE_URL = "https://meme-mining.xyz/public/api"
TIMEOUT = 15


class MemeMiningAPI:
    def __init__(self, session_token: str, name: str = "unknown"):
        self.session_token = session_token
        self.name = name
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })

    def _post(self, endpoint: str, data: dict = None, retries: int = 2) -> dict:
        url = f"{BASE_URL}/{endpoint}"
        payload = {"sessionToken": self.session_token}
        if data:
            payload.update(data)

        for attempt in range(retries):
            try:
                resp = self.session.post(url, json=payload, timeout=TIMEOUT)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.JSONDecodeError:
                logger.warning(f"[{self.name}] Non-JSON response from {endpoint}")
                return {"ok": False, "error": "non_json_response"}
            except requests.exceptions.RequestException as e:
                logger.warning(f"[{self.name}] {endpoint} attempt {attempt+1}/{retries}: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
        return {"ok": False, "error": "request_failed"}

    # ── Core ─────────────────────────────────────────

    def bootstrap(self) -> dict:
        """Get full game state."""
        return self._post("bootstrap.php")

    def finance_overview(self) -> dict:
        """Get finance overview."""
        return self._post("finance/overview.php")

    # ── Daily Bonus ──────────────────────────────────

    def daily_bonus_state(self) -> dict:
        """Get daily bonus status."""
        return self._post("daily-bonus/state.php")

    def daily_bonus_claim(self) -> dict:
        """Claim daily bonus."""
        return self._post("daily-bonus/claim.php")

    # ── Exchange ─────────────────────────────────────

    def exchange_hash(self) -> dict:
        """Exchange all hash to USD. Rate: 1M hash = $1."""
        return self._post("wallet/exchange-hash.php")

    # ── Miners ───────────────────────────────────────

    def buy_miner(self, miner_id: int) -> dict:
        """Buy a miner by ID."""
        return self._post("shop/buy-miner.php", {"minerId": miner_id})

    # ── Tasks ────────────────────────────────────────

    def task_list(self, mark_seen: bool = True) -> dict:
        """Get task list."""
        return self._post("tasks/list.php", {"markSeen": mark_seen})

    def task_claim(self, task_id: int) -> dict:
        """Claim a completed task."""
        return self._post("tasks/claim.php", {"taskId": task_id})

    # ── Season ───────────────────────────────────────

    def season_state(self) -> dict:
        """Get season state."""
        return self._post("season/state.php")

    def season_claim(self, mission_key: str) -> dict:
        """Claim season mission reward."""
        return self._post("season/claim.php", {"key": mission_key})

    def season_progress(self) -> dict:
        """Get season progress."""
        return self._post("season/progress.php")

    # ── Level ────────────────────────────────────────

    def profile_state(self) -> dict:
        """Get profile state."""
        return self._post("profile/state.php")

    def claim_level_reward(self, level: int = None) -> dict:
        """Claim level reward. If level not specified, use level from bootstrap."""
        data = {}
        if level:
            data["level"] = level
        return self._post("profile/claim-level.php", data)

    # ── Boost ────────────────────────────────────────

    def boost_state(self) -> dict:
        """Get boost state."""
        return self._post("boost/state.php")

    def boost_buy(self, minutes: int) -> dict:
        """Buy mining boost."""
        return self._post("boost/buy.php", {"minutes": minutes})

    # ── Referrals ────────────────────────────────────

    def referrals_overview(self) -> dict:
        """Get referrals overview."""
        return self._post("referrals/overview.php")

    # ── Finance ──────────────────────────────────────

    def create_payout(self, amount_usd: float, address: str, currency: str = "ton") -> dict:
        """Create withdrawal."""
        return self._post("finance/create-payout.php", {
            "amountUsd": amount_usd,
            "address": address,
            "currency": currency,
        })