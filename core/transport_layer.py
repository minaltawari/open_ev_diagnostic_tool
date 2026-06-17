import isotp

from config.user_config import (
    FUNCTIONAL_ID,
    ISOTP_PARAMS
)

def create_physical_stack(bus, tx_id, rx_id):

    addr = isotp.Address(
        rxid=rx_id,
        txid=tx_id
    )

    return isotp.CanStack(
        bus=bus,
        address=addr,
        params=ISOTP_PARAMS
    )

def create_functional_stack(bus, rx_id):

    addr = isotp.Address(
        rxid=rx_id,
        txid=FUNCTIONAL_ID
    )

    return isotp.CanStack(
        bus=bus,
        address=addr,
        params=ISOTP_PARAMS
    )
