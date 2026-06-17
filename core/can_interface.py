import can

from config.user_config import (
    MULTICAST_IP,
    MULTICAST_PORT
)

def init_hardware_bus():

    try:
        return can.Bus(
            interface='udp_multicast',
            channel=MULTICAST_IP,
            port=MULTICAST_PORT
        )

    except Exception as e:
        print(f"Bus Error : {e}")
        return None
