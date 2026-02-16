# scripts/src/image_budget.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

@dataclass
class BudgetConfig:
    # Limite mensal (USD)
    monthly_limit_usd: float = 15.0
    # Custo estimado por imagem (USD). Ajuste via env AO_COST_PER_IMAGE_USD.
    # Como preços podem mudar, deixamos configurável.
    cost_per_image_usd: float = 0.02
    # Pasta do ledger
    ledger_dir: Path = Path("output") / "budget"

def _month_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y-%m")

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_budget_config(project_root: Path) -> BudgetConfig:
    limit = float(os.getenv("AO_BUDGET_USD", "15").strip() or "15")
    cpi = float(os.getenv("AO_COST_PER_IMAGE_USD", "0.02").strip() or "0.02")
    return BudgetConfig(monthly_limit_usd=limit, cost_per_image_usd=cpi, ledger_dir=project_root / "output" / "budget")

def ledger_path(cfg: BudgetConfig) -> Path:
    return cfg.ledger_dir / "budget_ledger.json"

def get_month_spend(cfg: BudgetConfig, now: Optional[datetime] = None) -> Tuple[float, Dict[str, Any]]:
    path = ledger_path(cfg)
    data = _load_json(path) or {}
    month = _month_key(now)
    month_data = data.get(month) or {"spent_usd": 0.0, "items": []}
    spent = float(month_data.get("spent_usd", 0.0) or 0.0)
    return spent, data

def can_spend(cfg: BudgetConfig, estimate_usd: float, now: Optional[datetime] = None) -> Tuple[bool, float]:
    spent, _ = get_month_spend(cfg, now)
    remaining = cfg.monthly_limit_usd - spent
    return (estimate_usd <= remaining), remaining

def record_spend(
    cfg: BudgetConfig,
    amount_usd: float,
    kind: str,
    meta: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None
) -> None:
    now = now or datetime.now()
    month = _month_key(now)
    path = ledger_path(cfg)
    data = _load_json(path) or {}
    month_data = data.get(month) or {"spent_usd": 0.0, "items": []}

    month_data["spent_usd"] = float(month_data.get("spent_usd", 0.0) or 0.0) + float(amount_usd)
    item = {
        "ts": now.isoformat(timespec="seconds"),
        "kind": kind,
        "amount_usd": float(amount_usd),
        "meta": meta or {},
    }
    month_data["items"].append(item)
    data[month] = month_data
    _save_json(path, data)
