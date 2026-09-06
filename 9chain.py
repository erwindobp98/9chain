import base64
import datetime
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

BASE_URL = "https://api.9chain.com/v2"
TOKENS_FILE = Path("tokens.json")
RESULTS_FILE = Path("login_results.json")

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Origin": "https://www.9chain.com",
    "Referer": "https://www.9chain.com/",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
}

KNOWN_COMPONENTS = [
    "cpu",
    "ram",
    "firewall",
    "anti_sybil",
    "peer_connections",
    "relay_nodes",
    "consensus_tuner",
    "sharding",
]

THREAD_LOCAL = threading.local()


def get_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        THREAD_LOCAL.session = session
    return session


class ApiError(RuntimeError):
    def __init__(self, message: str, *, is_max_constraint: bool = False):
        super().__init__(message)
        self.is_max_constraint = is_max_constraint


def ask(question: str) -> str:
    return input(question).strip()


def load_accounts(path: str | Path = "accounts.json") -> List[Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {p}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Format JSON tidak valid pada {p}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("accounts.json harus berupa array/list akun.")

    accounts: List[Dict[str, str]] = []
    for i, account in enumerate(data, start=1):
        if not isinstance(account, dict):
            raise ValueError(f"Akun #{i} harus berupa object JSON.")

        email = str(account.get("email", "")).strip()
        password = str(account.get("password", ""))

        if not email:
            raise ValueError(f"Akun #{i} tidak memiliki email.")
        if not password:
            raise ValueError(f"Akun #{i} ({email}) tidak memiliki password.")

        accounts.append({"email": email, "password": password})

    return accounts


def load_token_cache() -> Dict[str, str]:
    if not TOKENS_FILE.exists():
        return {}
    try:
        data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_token_cache(cache: Dict[str, str]) -> None:
    TOKENS_FILE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def decode_jwt_exp(token: str) -> Optional[int]:
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        parsed = json.loads(raw.decode("utf-8"))
        exp = parsed.get("exp")
        return int(exp * 1000) if exp else None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def is_token_valid(token: str) -> bool:
    exp_ms = decode_jwt_exp(token)
    if not exp_ms:
        return False
    return exp_ms - int(time.time() * 1000) > 60_000


def response_json(res: requests.Response) -> Dict[str, Any]:
    try:
        data = res.json()
    except ValueError:
        raise ApiError(f"{res.status_code} response bukan JSON: {res.text[:500]}")
    if not isinstance(data, dict):
        raise ApiError(f"{res.status_code} format response tidak dikenal: {data!r}")
    return data


def auth_headers(token: str) -> Dict[str, str]:
    return {
        **HEADERS_BASE, 
        "Authorization": f"Bearer {token}",
    }


def login(email: str, password: str) -> str:
    res = get_session().post(
        f"{BASE_URL}/auth/login",
        headers=HEADERS_BASE,
        json={"email": email, "password": password},
        timeout=30,
    )
    data = response_json(res)
    if not res.ok or not data.get("success"):
        raise ApiError(f"{res.status_code} {json.dumps(data, ensure_ascii=False)}")
    try:
        return data["data"]["accessToken"]
    except (KeyError, TypeError):
        raise ApiError(f"Login sukses tetapi accessToken tidak ditemukan: {data}")


def get_token(email: str, password: str, token_cache: Dict[str, str]) -> tuple[str, bool]:
    cached = token_cache.get(email)
    if cached and is_token_valid(cached):
        return cached, True

    token = login(email, password)
    token_cache[email] = token
    return token, False


def api_request(
    method: str,
    path: str,
    token: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> tuple[requests.Response, Dict[str, Any]]:
    res = get_session().request(
        method,
        f"{BASE_URL}{path}",
        headers=auth_headers(token),
        json=payload,
        timeout=timeout,
    )
    return res, response_json(res)


def set_profile_country(token: str, country: str = "ID") -> Dict[str, Any]:
    res, data = api_request("PATCH", "/me/profile", token, payload={"country": country})
    if not res.ok or not data.get("success"):
        raise ApiError(f"set profile gagal: {res.status_code} {json.dumps(data, ensure_ascii=False)}")
    return data.get("data", {})


def enter_program(token: str) -> Dict[str, Any]:
    res, data = api_request("POST", "/program/enter", token)
    if not res.ok or not data.get("success"):
        raise ApiError(f"enter program gagal: {res.status_code} {json.dumps(data, ensure_ascii=False)}")
    return data.get("data", {})


def ensure_program_ready(token: str, country: str = "ID") -> None:
    set_profile_country(token, country)
    enter_program(token)


def check_in(token: str) -> Dict[str, Any]:
    status_res, status = api_request("GET", "/me/check-in", token)
    if not status_res.ok or not status.get("success"):
        raise ApiError(
            f"check-in status gagal: {status_res.status_code} "
            f"{json.dumps(status, ensure_ascii=False)}"
        )

    status_data = status.get("data") or {}
    if not status_data.get("canCheckIn"):
        return {
            "claimed": False,
            "reason": "sudah check-in hari ini",
            "streak": status_data.get("streak"),
        }

    claim_res, claim = api_request("POST", "/me/check-in", token)
    if not claim_res.ok or not claim.get("success"):
        raise ApiError(
            f"claim check-in gagal: {claim_res.status_code} "
            f"{json.dumps(claim, ensure_ascii=False)}"
        )

    claim_data = claim.get("data") or {}
    return {
        "claimed": True,
        "reward": claim_data.get("reward"),
        "streak": claim_data.get("streak"),
    }


def tap_once(token: str, count: int) -> Dict[str, Any]:
    res, data = api_request("POST", "/program/tap", token, payload={"count": count})

    if not res.ok or not data.get("success"):
        error = data.get("error") or {}
        details = error.get("details") or {}
        fields = details.get("fields") or []

        is_max_constraint = (
            error.get("code") == "VALIDATION_FAILED"
            and any(
                field.get("field") == "count"
                and "max" in (field.get("constraints") or [])
                for field in fields
                if isinstance(field, dict)
            )
        )
        raise ApiError(
            f"tap gagal: {res.status_code} {json.dumps(data, ensure_ascii=False)}",
            is_max_constraint=is_max_constraint,
        )

    return data.get("data") or {}


def tap_all(token: str, start_count: int = 100) -> Dict[str, Any]:
    batch_size = start_count
    last_result: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = []

    low = 1
    high = start_count

    while low < high:
        mid = (low + high + 1) // 2
        try:
            result = tap_once(token, mid)
            last_result = result
            history.append(result)
            low = mid
            batch_size = mid

            state = result.get("state") or {}
            if state.get("tapsRemaining", 0) <= 0:
                return {
                    "history": history,
                    "finalState": state,
                    "batchSizeFound": batch_size,
                }
        except ApiError as exc:
            if exc.is_max_constraint:
                high = mid - 1
            else:
                raise

        time.sleep(2.0)

    if batch_size < 1:
        raise ApiError("Tidak bisa menemukan batch size yang valid untuk tap.")

    while last_result is None or (last_result.get("state") or {}).get("tapsRemaining", 0) > 0:
        remaining = (
            (last_result.get("state") or {}).get("tapsRemaining", float("inf"))
            if last_result
            else float("inf")
        )
        next_count = int(min(batch_size, remaining)) if remaining != float("inf") else batch_size
        if next_count <= 0:
            break

        result = tap_once(token, next_count)
        last_result = result
        history.append(result)

        if (result.get("state") or {}).get("tapsRemaining", 0) <= 0:
            break
        time.sleep(2.0)

    final_state = (last_result or {}).get("state") or {}
    return {
        "history": history,
        "finalState": final_state,
        "batchSizeFound": batch_size,
    }


def is_country_required_error(message: str) -> bool:
    return "PROGRAM_COUNTRY_REQUIRED" in message


def get_state(token: str) -> Dict[str, Any]:
    res, data = api_request("GET", "/program/state", token)
    if not res.ok or not data.get("success"):
        raise ApiError(f"state gagal: {res.status_code} {json.dumps(data, ensure_ascii=False)}")
    return data


def get_catalog(token: str) -> List[Dict[str, Any]]:
    res, data = api_request("GET", "/program/catalog", token)
    if not res.ok or not data.get("success"):
        raise ApiError(f"catalog gagal: {res.status_code} {json.dumps(data, ensure_ascii=False)}")
    return ((data.get("data") or {}).get("components") or [])


def upgrade_once(token: str, component_key: str, to_level: int) -> Dict[str, Any]:
    res, data = api_request(
        "POST",
        "/program/upgrade",
        token,
        payload={"componentKey": component_key, "toLevel": to_level},
    )
    if not res.ok or not data.get("success"):
        raise ApiError(
            f"upgrade {component_key} gagal: {res.status_code} "
            f"{json.dumps(data, ensure_ascii=False)}"
        )
    return data.get("data") or {}


def upgrade_node_tier(token: str, to_tier: int) -> Dict[str, Any]:
    res, data = api_request(
        "POST",
        "/program/node/upgrade",
        token,
        payload={"toTier": to_tier},
    )
    if not res.ok or not data.get("success"):
        raise ApiError(
            f"upgrade node tier gagal: {res.status_code} "
            f"{json.dumps(data, ensure_ascii=False)}"
        )
    return data.get("data") or {}


def upgrade_components(token: str, selected_keys: Sequence[str]) -> List[Dict[str, Any]]:
    catalog = get_catalog(token)
    summary: List[Dict[str, Any]] = []

    for key in selected_keys:
        comp = next((c for c in catalog if c.get("componentKey") == key), None)

        if not comp:
            summary.append({"componentKey": key, "skipped": True, "reason": "komponen tidak ditemukan"})
            continue
        if not comp.get("unlocked"):
            summary.append({"componentKey": key, "skipped": True, "reason": "masih locked"})
            continue
        if comp.get("level", 0) >= comp.get("maxLevel", 0):
            summary.append({"componentKey": key, "skipped": True, "reason": "sudah max level"})
            continue

        next_level = int(comp.get("level", 0)) + 1
        try:
            result = upgrade_once(token, key, next_level)
            summary.append(
                {
                    "componentKey": key,
                    "levelFrom": result.get("levelFrom"),
                    "levelTo": result.get("levelTo"),
                    "cost": result.get("cost"),
                }
            )
        except Exception as exc:
            summary.append({"componentKey": key, "error": str(exc)})

        time.sleep(2.1)

    return summary


def upgrade_tier(token: str) -> Dict[str, Any]:
    state = get_state(token)
    state_data = state.get("data") or {}
    next_tier = state_data.get("nextTier")
    if not next_tier:
        return {"skipped": True, "reason": "sudah tier maksimal"}

    result = upgrade_node_tier(token, next_tier["tier"])
    return {
        "tierFrom": result.get("tierBefore"),
        "tierTo": result.get("tierAfter"),
        "cost": result.get("cost"),
    }


def with_program_retry(token: str, country: str, func):
    try:
        return func()
    except Exception as exc:
        if is_country_required_error(str(exc)):
            ensure_program_ready(token, country)
            try:
                return func()
            except Exception as retry_exc:
                return {"error": str(retry_exc)}
        return {"error": str(exc)}


# ----------------------------- Parallel / Rich runtime -----------------------------

try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    Live = None
    Table = None
    Panel = None

WIB_RESET_HOUR = 7
MAX_WORKERS = 20


def build_result_parts(res: Dict[str, Any]) -> List[str]:
    parts = []
    if "upgrade" in res and isinstance(res["upgrade"], list):
        for item in res["upgrade"]:
            if isinstance(item, dict):
                if item.get("levelTo"):
                    parts.append(f"{item.get('componentKey')}: lvl {item.get('levelFrom')}->{item.get('levelTo')}")
                elif item.get("reason"):
                    parts.append(f"{item.get('componentKey')}: {item.get('reason')}")
    if "tier" in res and isinstance(res["tier"], dict):
        t = res["tier"]
        if t.get("tierTo"):
            parts.append(f"Tier: {t.get('tierFrom')}->{t.get('tierTo')}")
        elif t.get("reason"):
            parts.append(f"Tier: {t.get('reason')}")
    return parts


def _safe_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def short_account(email: str) -> str:
    if "@" in email:
        name, domain = email.split("@", 1)
        return f"{name[:16]}@{domain[:18]}"
    return email[:30]


def extract_server_balance(state_response: Dict[str, Any]) -> Optional[float]:
    """Mengambil Saldo Aktif dari response API."""
    if not isinstance(state_response, dict):
        return None

    target_keys = ["balance", "currentbalance", "availablebalance", "spendablebalance", "points"]

    def _search_dict(d: dict) -> Optional[float]:
        for k, v in d.items():
            if k.lower() in target_keys:
                num = _safe_float(v)
                if num is not None:
                    return num
            if isinstance(v, dict):
                res = _search_dict(v)
                if res is not None:
                    return res
        return None

    return _search_dict(state_response)


def extract_node_tier(state_response: Dict[str, Any]) -> str:
    """Mengambil level Node Tier dari response API."""
    if not isinstance(state_response, dict):
        return "-"
    
    data = state_response.get("data") or state_response
    tier = data.get("nodeTier") or data.get("tier")
    if tier is not None:
        return f"Tier {tier}"
    return "-"


def make_dashboard(rows: List[Dict[str, Any]], phase: str, cycle: int, countdown: str = ""):
    table = Table(
        title=f"🚀 9CHAIN • {phase} • CYCLE #{cycle}",
        expand=True,
        show_lines=True,
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("ACCOUNT", no_wrap=True)
    table.add_column("LOGIN", no_wrap=True)
    table.add_column("DAILY", no_wrap=True)
    table.add_column("TAP-TAP", no_wrap=True)
    table.add_column("TIER", justify="center", no_wrap=True)
    table.add_column("DETAIL", overflow="ellipsis")

    for row in rows:
        tier_text = str(row.get("tier", "-"))

        table.add_row(
            str(row["index"]),
            short_account(row["email"]),
            str(row.get("login", "WAIT")),
            str(row.get("daily", "WAIT")),
            str(row.get("tap", "WAIT")),
            tier_text,
            str(row.get("detail", "")),
        )

    subtitle = f"Accounts: {len(rows)}"
    if countdown:
        subtitle += f" • Next daily: {countdown}"
    return Panel(table, subtitle=subtitle, border_style="bright_blue")


def save_results(results: List[Dict[str, Any]]):
    RESULTS_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch_account_info(row: Dict[str, Any], token_cache: Optional[Dict[str, str]] = None):
    """Mengambil informasi Tier dari server."""
    email = row.get("email")
    token = row.get("_token")

    if not email or not token:
        return

    try:
        data = get_state(token)
        row["tier"] = extract_node_tier(data)
    except Exception:
        pass


def _account_worker(account, token_cache_snapshot, action, selected_components=None):
    email = account["email"]
    password = account["password"]
    local_cache = {email: token_cache_snapshot.get(email)} if token_cache_snapshot.get(email) else {}

    token, from_cache = get_token(email, password, local_cache)
    result = {"email": email, "token": token, "tokenFromCache": from_cache}

    if action == "daily":
        result["checkin"] = with_program_retry(token, "ID", lambda: check_in(token))
    elif action == "tap":
        result["tap"] = with_program_retry(token, "ID", lambda: tap_all(token, 100))
    elif action == "upgrade":
        result["upgrade"] = with_program_retry(
            token, "ID", lambda: upgrade_components(token, selected_components or [])
        )
    elif action == "tier":
        result["tier"] = with_program_retry(token, "ID", lambda: upgrade_tier(token))

    return result


def _parallel_action(accounts, rows, token_cache, action, live, cycle, results, selected_components=None):
    phase_names = {
        "daily": "DAILY",
        "tap": "TAP-TAP",
        "upgrade": "UPGRADE",
        "tier": "TIER",
    }
    phase = phase_names[action]

    for row in rows:
        if action == "daily":
            row["daily"] = "RUNNING"
        elif action == "tap":
            row["tap"] = "RUNNING"
        row["detail"] = f"{phase} berjalan..."
    live.update(make_dashboard(rows, phase, cycle))

    snapshot = dict(token_cache)
    workers = min(MAX_WORKERS, max(1, len(accounts)))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="9chain") as executor:
        futures = {
            executor.submit(
                _account_worker,
                account,
                snapshot,
                action,
                selected_components,
            ): pos
            for pos, account in enumerate(accounts)
        }

        for future in as_completed(futures):
            pos = futures[future]
            row = rows[pos]
            try:
                result = future.result()
                token_cache[row["email"]] = result["token"]
                row["_token"] = result["token"]
                row["login"] = "CACHE" if result.get("tokenFromCache") else "LOGIN OK"
                row["status_result"] = result

                # Ambil info Tier saat aksi berjalan
                fetch_account_info(row, token_cache)

                if action == "daily":
                    checkin = result.get("checkin") or {}
                    if checkin.get("error"):
                        row["daily"] = "ERROR"
                        row["detail"] = checkin["error"][:100]
                    elif checkin.get("claimed"):
                        row["daily"] = "DONE"
                        row["detail"] = f"Reward +{checkin.get('reward')} | streak {checkin.get('streak')}"
                    else:
                        row["daily"] = "SKIP"
                        row["detail"] = "Sudah check-in hari ini"

                elif action == "tap":
                    tap = result.get("tap") or {}
                    if tap.get("error"):
                        row["tap"] = "ERROR"
                        row["detail"] = tap["error"][:100]
                    else:
                        final_state = tap.get("finalState") or {}
                        row["tap"] = "DONE"
                        row["detail"] = (
                            f"Tap batch={tap.get('batchSizeFound')} | "
                            f"remaining={final_state.get('tapsRemaining')}"
                        )

                elif action == "upgrade":
                    value = result.get("upgrade") or {}
                    res_parts = build_result_parts({"upgrade": value})
                    row["detail"] = res_parts[0] if res_parts else "Upgrade selesai"

                elif action == "tier":
                    value = result.get("tier") or {}
                    res_parts = build_result_parts({"tier": value})
                    row["detail"] = res_parts[0] if res_parts else "Tier selesai"

                results[pos].update(result)
                results[pos]["status"] = "success"
            except Exception as exc:
                results[pos].update({"email": row["email"], "error": str(exc), "status": "failed"})
                if action == "daily":
                    row["daily"] = "ERROR"
                elif action == "tap":
                    row["tap"] = "ERROR"
                row["detail"] = str(exc)[:120]

            save_token_cache(token_cache)
            live.update(make_dashboard(rows, phase, cycle))

    live.update(make_dashboard(rows, phase, cycle))


def seconds_until_next_daily(reset_hour=WIB_RESET_HOUR):
    from datetime import datetime, timedelta
    now = datetime.now()
    target = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def format_countdown(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def standby_until_reset(rows: List[Dict[str, Any]], cycle: int, live: Any):
    """Standby countdown murni tanpa background request ke server."""
    while True:
        remaining = seconds_until_next_daily()
        countdown = format_countdown(remaining)
        
        if remaining <= 1.0:
            return

        live.update(make_dashboard(rows, "IDLE (STANDBY)", cycle, countdown=countdown))
        time.sleep(1.0)


def run_daily_tap_mining_loop(accounts, token_cache):
    rows = [
        {
            "index": i,
            "email": acc["email"],
            "login": "WAIT",
            "daily": "WAIT",
            "tap": "WAIT",
            "tier": "-",
            "detail": "Menunggu...",
        }
        for i, acc in enumerate(accounts, start=1)
    ]
    results = [{"email": acc["email"]} for acc in accounts]
    cycle = 0

    if Live is None:
        raise RuntimeError("Rich belum terinstall. Jalankan: pip install requests rich")

    with Live(make_dashboard(rows, "STARTING", cycle), refresh_per_second=4, screen=True) as live:
        while True:
            cycle += 1
            for row in rows:
                row["daily"] = "WAIT"
                row["tap"] = "WAIT"
                row["detail"] = "Memulai siklus harian..."
            live.update(make_dashboard(rows, "DAILY", cycle))

            # 1) DAILY
            _parallel_action(accounts, rows, token_cache, "daily", live, cycle, results)

            # 2) TAP-TAP
            _parallel_action(accounts, rows, token_cache, "tap", live, cycle, results)
            save_results(results)

            # 3) Standby Tanpa Server Polling Hingga Reset Harian
            standby_until_reset(rows, cycle, live)


def choose_mode() -> str:
    print("\nPilih mode aksi:")
    print("  1) Daily check-in saja")
    print("  2) Tap-tap saja (max 100/request)")
    print("  3) Daily + Tap-tap Loop (Auto Standby Reset Harian)")
    print("  4) Upgrade (komponen)")
    print("  5) Upgrade Tier")
    mode_map = {"1": "daily", "2": "tap", "3": "both", "4": "upgrade", "5": "tier"}
    mode = mode_map.get(ask("\nPilihan (1/2/3/4/5): "))
    if not mode:
        raise ValueError("Pilihan tidak valid.")
    return mode


def choose_components_all_accounts(accounts, token_cache):
    ref = accounts[0]
    token, _ = get_token(ref["email"], ref["password"], token_cache)
    token_cache[ref["email"]] = token
    save_token_cache(token_cache)
    catalog = get_catalog(token)
    state = get_state(token)
    bal = extract_server_balance(state)
    tier = extract_node_tier(state)
    
    print(f"\n[Akun Acuan: {ref['email']}]")
    print(f"Saldo Aktif : {bal:,.2f}" if bal is not None else "Saldo Aktif : -")
    print(f"Node Tier   : {tier}\n")
    print("Komponen yang bisa di-upgrade:")

    menu_items = []
    for key in KNOWN_COMPONENTS:
        comp = next((c for c in catalog if c.get("componentKey") == key), None)
        menu_items.append((key, comp))

    for idx, (key, comp) in enumerate(menu_items, start=1):
        if not comp:
            print(f"  {idx}) {key} - data tidak ditemukan")
        elif not comp.get("unlocked"):
            print(f"  {idx}) {key} - LOCKED")
        elif comp.get("level", 0) >= comp.get("maxLevel", 0):
            print(f"  {idx}) {key} - {comp.get('level')}/{comp.get('maxLevel')} MAX")
        else:
            print(f"  {idx}) {key} - {comp.get('level')} -> {comp.get('level', 0)+1}, cost: {comp.get('nextCost')}")

    all_no = len(menu_items) + 1
    print(f"  {all_no}) semua yang unlocked & belum max")
    choice = ask("\nPilihan (contoh: 1,2 atau nomor 'semua'): ")
    if choice == str(all_no):
        selected = [key for key, comp in menu_items if comp and comp.get("unlocked") and comp.get("level", 0) < comp.get("maxLevel", 0)]
    else:
        selected = []
        for part in choice.split(","):
            try:
                n = int(part.strip())
            except ValueError:
                continue
            if 1 <= n <= len(KNOWN_COMPONENTS):
                selected.append(KNOWN_COMPONENTS[n - 1])
    selected = list(dict.fromkeys(selected))
    if not selected:
        raise ValueError("Tidak ada komponen valid yang dipilih.")
    return selected


def preview_tier_all_accounts(accounts, token_cache):
    ref = accounts[0]
    token, _ = get_token(ref["email"], ref["password"], token_cache)
    token_cache[ref["email"]] = token
    save_token_cache(token_cache)
    state = get_state(token)
    bal = extract_server_balance(state)
    tier = extract_node_tier(state)
    
    print(f"\n[Akun Acuan: {ref['email']}]")
    print(f"Saldo Aktif : {bal:,.2f}" if bal is not None else "Saldo Aktif : -")
    print(f"Node Tier   : {tier}")
    
    state_data = state.get("data") or {}
    next_tier = state_data.get("nextTier")
    if next_tier:
        suffix = "" if next_tier.get("affordable") else " (saldo tidak cukup)"
        print(f"Next Tier   : Tier {next_tier.get('tier')} (Cost: {next_tier.get('cost')}){suffix}")
    else:
        print("Status      : Sudah di tier maksimal.")
    return ask("\nLanjutkan upgrade tier untuk SEMUA akun? (y/n): ").lower() == "y"


def main() -> None:
    try:
        accounts = load_accounts()
        if not accounts:
            raise ValueError("accounts.json tidak memiliki akun.")
        token_cache = load_token_cache()

        print(f"\nTotal akun dari accounts.json: {len(accounts)}")
        print("Semua akun akan diproses bersamaan sesuai urutan accounts.json.")
        mode = choose_mode()

        if mode == "both":
            run_daily_tap_mining_loop(accounts, token_cache)
            return

        if Live is None:
            raise RuntimeError("Rich belum terinstall. Jalankan: pip install requests rich")

        selected_components = []
        if mode == "upgrade":
            selected_components = choose_components_all_accounts(accounts, token_cache)
        if mode == "tier" and not preview_tier_all_accounts(accounts, token_cache):
            print("Dibatalkan.")
            return

        rows = [
            {"index": i, "email": a["email"], "login": "WAIT", "daily": "WAIT", "tap": "WAIT", "tier": "-", "detail": "Menunggu..."}
            for i, a in enumerate(accounts, 1)
        ]
        results = [{"email": a["email"]} for a in accounts]

        with Live(make_dashboard(rows, mode.upper(), 1), refresh_per_second=4, screen=True) as live:
            _parallel_action(accounts, rows, token_cache, mode, live, 1, results, selected_components)
        save_results(results)
        print(f"\nSelesai. Hasil: {RESULTS_FILE} | Token: {TOKENS_FILE}")

    except KeyboardInterrupt:
        print("\nDihentikan pengguna.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
