# ==========================================================
# USER CONFIGURATION FILE
# Users can modify these settings without touching core code
# ==========================================================

# ECU Addressing

TARGET_TX_ID = 0x7E0
TARGET_RX_ID = 0x7E8
FUNCTIONAL_ID = 0x7DF

# Network Settings

CAN_INTERFACE = "pcan"
CAN_CHANNEL = "PCAN_USBBUS2"
BITRATE = 500000

# ISO-TP Parameters

ISOTP_PARAMS = {
    "stmin": 10,
    "blocksize": 8,
    "tx_padding": 0x00
}

# UDS Settings

SUPPORTED_SIDS = [0x10, 0x22, 0x19, 0x14, 0x3E]
TWO_BYTE_IDENTIFIER_SIDS = [0x22, 0x2E]
ONE_BYTE_IDENTIFIER_SIDS = [0x10, 0x19, 0x14]


DEFAULT_TIMEOUT = 15

TESTER_PRESENT_INTERVAL = 2
