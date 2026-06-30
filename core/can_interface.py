import can

from config.user_config import (
    CAN_INTERFACE,
    CAN_CHANNEL,
    CAN_SETTING
)

def init_hardware_bus():

    try:
        return can.Bus(
            interface=CAN_INTERFACE,
            channel=CAN_CHANNEL,
            port=CAN_SETTING
        )

    except Exception as e:
        print(f"Bus Error : {e}")
        return None
