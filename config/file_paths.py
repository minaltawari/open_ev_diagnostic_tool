import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECODE_FILE = os.path.join(
    ROOT_DIR,
    "config",
    "decode_values.xlsx"
)

STATE_FILE = os.path.join(
    ROOT_DIR,
    "config",
    "ev_state_final.xlsx"
)
