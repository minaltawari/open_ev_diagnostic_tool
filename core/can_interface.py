import can

from config.user_config import (
    PCAN_INTERFACE,
    PCAN_CHANNEL,
    BITRATE,
)

def init_hardware_bus():

    try:
        return can.Bus(
            interface=CAN_INTERFACE,
            channel=PCAN_CHANNEL,
            bitrate=BITRATE
        )

    except Exception as e:
        print(f"Bus Error : {e}")
        return None
