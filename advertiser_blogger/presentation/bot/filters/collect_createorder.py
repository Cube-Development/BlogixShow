def is_collect_createorder_state(current_state: str | None) -> bool:
    return bool(current_state and str(current_state).startswith("CollectCreateorderState"))
