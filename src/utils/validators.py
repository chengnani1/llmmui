from typing import Any, Dict, List


def validate_result_json_chains(chains: Any) -> List[Dict[str, Any]]:
    if not isinstance(chains, list):
        raise ValueError("result.json must be a list")

    for idx, item in enumerate(chains):
        if not isinstance(item, dict):
            raise ValueError(f"chain[{idx}] must be an object")
        for key in ("ui_before_grant", "ui_granting", "ui_after_grant"):
            if key not in item:
                raise ValueError(f"chain[{idx}] missing required field: {key}")
    return chains


def validate_scene_results(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("scene result must be a list")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"scene[{idx}] must be an object")
        if "chain_id" not in item:
            raise ValueError(f"scene[{idx}] missing chain_id")
    return items


def validate_permission_results(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("permission result must be a list")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"permission[{idx}] must be an object")
        if "chain_id" not in item:
            raise ValueError(f"permission[{idx}] missing chain_id")
    return items
