"""
MemeMiningBot — Automated bot for @MemeMiningBot Telegram game.
Handles: daily bonus, hash exchange, miner purchasing, tasks, season claims.
"""
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from api import MemeMiningAPI

# ── Config ───────────────────────────────────────────

LOG_FILE = Path(__file__).parent / "meme_miner.log"
CONFIG_FILE = Path(__file__).parent / "config.json"

# Telegram config (loaded from config.json on startup)
TELEGRAM_BOT_TOKEN = "8702206830:AAFuhBdm_DOXGc6Q-Lf_9ffG8NC14NXTzaQ"
TELEGRAM_CHAT_ID = "1079809191"
TELEGRAM_ENABLED = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MemeMiner")


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)


# ── Telegram Reporting ────────────────────────────────

def send_telegram(text: str, disable_notification: bool = False) -> bool:
    """Send a Telegram message via bot."""
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        import requests as _req
        resp = _req.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_notification": disable_notification,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[Telegram] Failed to send: {e}")
        return False


def report_cycle_complete(cycle_results: list, cycle_start: datetime):
    """Send summary report after all accounts in a cycle are done."""
    elapsed = (datetime.now() - cycle_start).total_seconds()
    lines = [
        "🤖 <b>MemeMiningBot — Cycle Report</b>",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"⏱ Duration: {int(elapsed)}s",
        "",
    ]
    for r in cycle_results:
        acct_name = r.get("name", "?")
        status = "✅" if r.get("status") == "ok" else "❌"
        usd = r.get("usd", 0)
        lvl = r.get("level", 0)
        actions = []
        if r.get("daily_claimed"):
            actions.append("daily")
        if r.get("season_claimed"):
            actions.append("season")
        if r.get("miner_bought"):
            actions.append(f"miner({r['miner_bought']})")
        if r.get("saving_for"):
            actions.append(f"save({r['saving_for']})")
        action_str = " | ".join(actions) if actions else "no action"
        lines.append(
            f"{status} <b>{acct_name}</b> | ${usd:.4f} | Lv{lvl} | {action_str}"
        )

    total_usd = sum(r.get("usd", 0) for r in cycle_results)
    lines.append("")
    lines.append(f"💰 Total balance: ${total_usd:.4f}")
    send_telegram("\n".join(lines))


# ── Helpers ──────────────────────────────────────────

def fmt_balance(data: dict) -> str:
    """Format balance from bootstrap/finance data."""
    user = data.get("user", data)
    b = user.get("balances", {})
    m = user.get("mining", {})

    usd = b.get("usd", 0)
    gems = b.get("gems", 0)
    hash_bal = m.get("hashBalance", 0)
    hash_rate = m.get("hashRate", 0)
    miners = m.get("ownedMinersCount", 0)
    level = user.get("level", 0)
    xp = user.get("experience", 0)

    return (
        f"💵 ${usd:.4f} | 💎 {gems} gems | ⛏ {hash_bal:.1f} hash "
        f"({hash_rate:.4f}/h) | Lv{level} ({xp}xp) | 🏭 {miners} miners"
    )
# ── Helpers ──────────────────────────────────────────

def find_next_miner_cost(miners: list) -> float | None:
    """Return price of cheapest buyable miner (canBuy=True, quantity > 0), or None."""
    available = [m for m in miners if m.get("canBuy") and m.get("quantity", 0) > 0]
    if not available:
        return None
    available.sort(key=lambda m: m.get("priceUsd", 99999))
    return available[0]["priceUsd"]


def get_cheapest_upgrade(miners: list, current_usd: float, reserve_usd: float = 0) -> dict | None:
    """Find the cheapest affordable miner.

    Strategy: buy the cheapest miner whose per-hash cost is lowest.
    Only consider miners where canBuy=True, quantity>0, and price <= (current_usd - reserve).
    A reserve keeps USD fluid so the account can save toward a bigger miner goal.
    """
    spend_limit = current_usd - reserve_usd
    affordable = [
        m for m in miners
        if m.get("canBuy") and m.get("quantity", 0) > 0 and m.get("priceUsd", 0) <= spend_limit
    ]
    if not affordable:
        return None

    # Sort by price (cheapest first) — simple strategy for early game
    affordable.sort(key=lambda m: m.get("priceUsd", 99999))
    return affordable[0]


def get_best_roi_miner(miners: list, current_usd: float, reserve_usd: float = 0) -> dict | None:
    """Find miner with best hash-per-dollar ratio that we can afford."""
    spend_limit = current_usd - reserve_usd
    affordable = [
        m for m in miners
        if m.get("canBuy") and m.get("quantity", 0) > 0 and m.get("priceUsd", 0) <= spend_limit
    ]
    if not affordable:
        return None

    # Best ROI: hashRate / priceUsd (higher is better)
    affordable.sort(
        key=lambda m: m.get("hashRate", 0) / max(m.get("priceUsd", 0.01), 0.01),
        reverse=True,
    )
    return affordable[0]


def _claim_daily_from_bootstrap(daily_bonus: dict) -> dict | None:
    """Check bootstrap dailyBonus.items for a claimable free daily reward.
    Returns the day-item dict if something can be claimed, else None.
    """
    for item in daily_bonus.get("items", []):
        if item.get("isFreeActive") and item.get("free", {}).get("canClaim"):
            return item
    return None


# ── Bot Loop ─────────────────────────────────────────

def process_account(api: MemeMiningAPI, config: dict) -> dict:
    """Process one account — single iteration of the main loop."""
    settings = config.get("settings", {})
    stats = {}

    # 1. Bootstrap — get current state
    logger.info(f"[{api.name}] 🔍 Fetching game state...")
    boot = api.bootstrap()
    if not boot.get("ok"):
        logger.error(f"[{api.name}] ❌ Bootstrap failed: {boot.get('error')}")
        return {"status": "error", "error": boot.get("error")}

    user = boot.get("user", {})
    stats["usd"] = user.get("balances", {}).get("usd", 0)
    stats["hash"] = user.get("mining", {}).get("hashBalance", 0)
    stats["level"] = user.get("level", 0)
    logger.info(f"[{api.name}] {fmt_balance(boot)}")

    # 2. Claim daily bonus (parse from bootstrap — daily-bonus/state.php returns empty bonuses)
    if settings.get("auto_daily_bonus"):
        daily_bonus_data = boot.get("dailyBonus", {})
        claimable_day = _claim_daily_from_bootstrap(daily_bonus_data)
        if claimable_day:
            claim = api.daily_bonus_claim()
            if claim.get("ok"):
                reward = claim.get("reward", {})
                logger.info(
                    f"[{api.name}] 🎁 Daily bonus claimed! Day {claimable_day.get('day')} "
                    f"— +${reward.get('usd', 0):.4f}"
                )
                stats["daily_claimed"] = True
            else:
                logger.warning(f"[{api.name}] ⚠️ Daily claim failed: {claim.get('error')}")
        else:
            streak = daily_bonus_data.get("streakLength", 0)
            next_day = daily_bonus_data.get("freeCycle", 0)
            logger.info(f"[{api.name}] ℹ️ Daily bonus done today (streak day {streak}). Next free cycle: {next_day}")

# 3. Claim level rewards (must claim sequentially from lowest unclaimed level)
    # Use levelRewards.items to find levels with status="claimable", then claim each
    if settings.get("auto_level_claim"):
        level_rewards = user.get("levelRewards", {})
        items = level_rewards.get("items", [])
        claimable_items = [it for it in items if it.get("status") == "claimable"]
        if claimable_items:
            # Claim in order (levels are usually ascending)
            for item in claimable_items:
                lvl = item.get("level")
                lr = api.claim_level_reward(level=lvl)
                if lr.get("ok"):
                    reward = lr.get("reward", {})
                    logger.info(
                        f"[{api.name}] 🏆 Level {lvl} reward claimed! "
                        f"+${reward.get('usd', 0):.4f} +{reward.get('gems', 0)} gems"
                    )
                else:
                    # 422 = level not claimable yet (must claim lower levels first)
                    logger.warning(f"[{api.name}] ⚠️ Level {lvl} claim failed: {lr.get('error')}")
                    break  # stop — next levels also won't work

    # 4. Exchange hash to USD (lower threshold so hash converts more often)
    current_hash = user.get("mining", {}).get("hashBalance", 0)
    # Threshold lowered from 500 to 50 — at 0.024/h, 500 hash needs 870h; 50 hash needs 87h
    threshold = settings.get("exchange_threshold_hash", 50)

    if current_hash >= threshold:
        exch = api.exchange_hash()
        if exch.get("ok"):
            usd_gained = exch.get("exchangedUsd", 0)
            hash_spent = exch.get("hashSpent", 0)
            logger.info(f"[{api.name}] 💱 Exchanged {hash_spent} hash → +${usd_gained:.6f}")
            stats["usd"] = exch.get("user", {}).get("balances", {}).get("usd", stats["usd"])
            # Update hash for next check
            stats["hash"] = exch.get("user", {}).get("mining", {}).get("hashBalance", 0)
        else:
            logger.warning(f"[{api.name}] ⚠️ Exchange failed: {exch.get('error')}")

    # 5. Process tasks
    if settings.get("auto_tasks"):
        tasks_resp = api.task_list(mark_seen=True)
        if tasks_resp.get("ok"):
            tasks = tasks_resp.get("tasks", [])
            for task in tasks:
                if task.get("status") == "ready":
                    t_claim = api.task_claim(task["id"])
                    if t_claim.get("ok"):
                        logger.info(f"[{api.name}] ✅ Task claimed: {task.get('title', task.get('slug', '?'))}")
                        stats["tasks_claimed"] = stats.get("tasks_claimed", 0) + 1

    # 6. Season missions
    if settings.get("auto_season_claim"):
        season = api.season_state()
        if season.get("ok"):
            missions = season.get("season", {}).get("missions", [])
            for mission in missions:
                if mission.get("canClaim"):
                    s_claim = api.season_claim(mission["key"])
                    if s_claim.get("ok"):
                        logger.info(f"[{api.name}] 🎯 Season reward claimed: {mission.get('titleKey', mission.get('key'))}")
                        stats["season_claimed"] = stats.get("season_claimed", 0) + 1

    # 7. Buy miners (if auto-buy enabled)
    if settings.get("auto_buy_cheapest"):
        # Re-fetch bootstrap to get latest balance after exchanges
        boot2 = api.bootstrap()
        if boot2.get("ok"):
            user2 = boot2.get("user", {})
            miners = user2.get("mining", {}).get("miners", [])
            current_usd = user2.get("balances", {}).get("usd", 0)
            strategy = settings.get("buy_strategy", "cheapest_upgrade")

            # Calculate the cheapest next miner to know our savings goal
            next_cost = find_next_miner_cost(miners)
            if next_cost:
                # Reserve 80% of the next miner's cost — keep 20% spendable for impulse buys
                reserve_usd = next_cost * 0.80
                target_usd = next_cost
                savings_needed = max(0, target_usd - current_usd)
                logger.info(
                    f"[{api.name}] 🎯 Next miner: ${target_usd:.2f} | "
                    f"Current: ${current_usd:.4f} | Need: ${savings_needed:.4f} more | "
                    f"Reserve: ${reserve_usd:.4f}"
                )

                if strategy == "best_roi":
                    best = get_best_roi_miner(miners, current_usd, reserve_usd=reserve_usd)
                else:
                    best = get_cheapest_upgrade(miners, current_usd, reserve_usd=reserve_usd)

                if best:
                    logger.info(
                        f"[{api.name}] 🛒 Buying {best['title']} "
                        f"(${best['priceUsd']:.2f}, hashrate +{best['hashRate']:.4f}/h)"
                    )
                    buy = api.buy_miner(best["id"])
                    if buy.get("ok"):
                        logger.info(f"[{api.name}] ✅ Bought {best['title']}!")
                        stats["miner_bought"] = best["title"]
                        new_balance = buy.get("user", {}).get("balances", {}).get("usd", 0)
                        stats["usd"] = new_balance
                    else:
                        logger.warning(f"[{api.name}] ❌ Buy failed: {buy.get('error')}")
                else:
                    # Can't afford anything even without reserve — show savings progress
                    if next_cost and savings_needed > 0:
                        logger.info(
                            f"[{api.name}] 💰 Saving for {find_next_miner_cost(miners)} miner "
                            f"— ${savings_needed:.4f} more needed"
                        )
                        stats["saving_for"] = "next miner"
                        stats["saving_needed"] = round(savings_needed, 4)

    stats["status"] = "ok"
    return stats


def run_single(config: dict):
    """Run bot for all accounts once."""
    for acct in config.get("accounts", []):
        token = acct.get("session_token", "").strip()
        if not token:
            logger.error(f"[{acct.get('name')}] ❌ No session token")
            continue

        api = MemeMiningAPI(token, name=acct.get("name", "unknown"))
        try:
            result = process_account(api, config)
            logger.info(f"[{api.name}] 📊 Result: {json.dumps(result, default=str)}")
        except Exception as e:
            logger.error(f"[{api.name}] ❌ Error: {e}")
            traceback.print_exc()


def run_loop(config: dict):
    """Run bot in continuous loop."""
    delay = config.get("settings", {}).get("loop_delay", 300)
    logger.info(f"🔄 Starting loop — delay={delay}s")
    
    while True:
        run_single(config)
        logger.info(f"⏳ Waiting {delay}s...")
        time.sleep(delay)


def run_queue(config: dict, delay_between: int = 300):
    """Run all accounts sequentially with delay between each, then report."""
    accounts = config.get("accounts", [])
    settings = config.get("settings", {})
    logger.info(f"📋 Queue mode — {len(accounts)} accounts, delay={delay_between}s")

    while True:
        cycle_start = datetime.now()
        cycle_results = []  # ← collect per-account results

        for i, acct in enumerate(accounts):
            name = acct.get("name", f"acct{i+1}")
            token = acct.get("session_token", "").strip()
            if not token:
                logger.warning(f"[{name}] ⛔ No token, skipping")
                continue

            api = MemeMiningAPI(token, name=name)
            try:
                result = process_account(api, config)
                result["name"] = name  # attach name for report
                cycle_results.append(result)

                stats_str = ""
                if result.get("miner_bought"):
                    stats_str += f"🛒 {result['miner_bought']} | "
                stats_str += f"💵 ${result.get('usd', 0):.4f}"

                if result.get("saving_for"):
                    stats_str += f" | 🎯 saving for {result['saving_for']} (${result.get('saving_needed', 0):.2f} more)"

                logger.info(f"[{name}] ✅ Done — {stats_str}")
            except Exception as e:
                logger.error(f"[{name}] ❌ {e}")
                traceback.print_exc()
                cycle_results.append({"name": name, "status": "error", "usd": 0, "level": 0})

            # Delay between accounts
            if i < len(accounts) - 1:
                logger.info(f"⏳ Waiting {delay_between}s before next account...")
                time.sleep(delay_between)

        # ── Cycle done — send Telegram report ──
        logger.info(f"📊 Sending cycle report...")
        report_cycle_complete(cycle_results, cycle_start)

        # Delay before next cycle
        loop_delay = settings.get("loop_delay", 600)
        logger.info(f"🔄 Cycle complete. Waiting {loop_delay}s...")
        time.sleep(loop_delay)


# ── Main ─────────────────────────────────────────────

def main():
    config = load_config()

    if "--once" in sys.argv:
        logger.info("▶ Running single iteration...")
        run_single(config)
    elif "--queue" in sys.argv:
        delay = 300
        if "--queue-delay" in sys.argv:
            try:
                idx = sys.argv.index("--queue-delay")
                delay = int(sys.argv[idx + 1])
            except (ValueError, IndexError):
                pass
        run_queue(config, delay_between=delay)
    else:
        run_loop(config)


if __name__ == "__main__":
    main()