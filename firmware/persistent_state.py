import json


STATE_FILE_PATH = "/persistent_state/state"
STATE_DEFAULT = {
    "restart_count": 0,
}


def save(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f)


def load():
    try:
        with open(STATE_FILE_PATH) as f:
            state = json.load(f)
    except FileNotFoundError:
        return STATE_DEFAULT

    return state


def set_restart_count(count):
    new_state = load()
    new_state["restart_count"] = count
    save(new_state)


def inc_restart_count():
    new_state = load()
    new_state["restart_count"] += 1
    save(new_state)


def reset_restart_count():
    set_restart_count(0)
