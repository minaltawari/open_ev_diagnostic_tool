# ==========================================================
# MAIN APPLICATION
# ==========================================================
# ==========================================================
# MAIN APPLICATION
# ==========================================================
import os
import sys

# Force Python to look at the workspace root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.can_interface import init_hardware_bus

from core.transport_layer import (
    create_physical_stack,
    create_functional_stack
)

from core.diagnostic_engine import DiagnosticEngine

from core.uds_layer import (
    evaluate_response
)

from core.translator import Translator

from core.tester_present import TesterPresentManager

from config.user_config import *

import sys


def main():

    print("==================================================")
    print("  STRICT SIDs (10, 22, 3E, 19, 14) DIAGNOSTIC TOOL")
    print(
        f"   [DIRECT TRANSMIT PORT MAP: "
        f"0x{TARGET_TX_ID:X} -> 0x{TARGET_RX_ID:X}]"
    )
    print("==================================================")

    # --------------------------------------------------
    # INITIALIZE CAN BUS
    # --------------------------------------------------

    bus = init_hardware_bus()

    if not bus:

        print("[-] Failed to initialize CAN Bus.")
        return

    # --------------------------------------------------
    # CREATE ISO-TP STACKS
    # --------------------------------------------------

    physical_stack = create_physical_stack(
        bus,
        TARGET_TX_ID,
        TARGET_RX_ID
    )

    functional_stack = create_functional_stack(
        bus,
        TARGET_RX_ID
    )

    # --------------------------------------------------
    # CORE OBJECTS
    # --------------------------------------------------

    engine = DiagnosticEngine(
        physical_stack
    )

    translator = Translator()

    tester_present = TesterPresentManager(
        engine
    )

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------

    while True:

        print("\n------------------------------------------------")

        request = input(
            "Enter Raw UDS Request Command (or 'Q' to quit): "
        ).strip()

        # ------------------------------------------
        # EXIT TOOL
        # ------------------------------------------

        if request.lower() == "q":

            tester_present.stop()

            print(
                "\n[*] De-allocating interfaces and shutting down CAN bus..."
            )

            try:
                bus.shutdown()
            except:
                pass

            print(
                "[+] Tool Closed Successfully"
            )

            sys.exit(0)

        if not request:
            continue

        # ------------------------------------------
        # HEX VALIDATION
        # ------------------------------------------

        try:

            payload = bytes.fromhex(
                request.replace(" ", "")
            )

        except ValueError:

            print(
                "[-] Invalid Hex format sequence."
            )

            continue

        sid = payload[0]

        # ------------------------------------------
        # SID VALIDATION
        # ------------------------------------------

        if sid not in SUPPORTED_SIDS:

            print(
                f"[-] Unsupported Service Identifier: "
                f"0x{sid:02X}"
            )

            continue

        # ------------------------------------------
        # EXTRACT DID / SUBFUNCTION
        # ------------------------------------------

        if sid in TWO_BYTE_IDENTIFIER_SIDS and len(payload) >= 3:

            target_id = (
                (payload[1] << 8)
                | payload[2]
            )

        elif len(payload) >= 2:

            target_id = payload[1]

        else:

            target_id = 0x00

        # ------------------------------------------
        # TRANSMIT REQUEST
        # ------------------------------------------

        print(
            f"[TX 0x{TARGET_TX_ID:X}] Transmitting to Target ECU..."
        )

        try:

            engine.send(payload)

        except Exception as e:

            print(
                f"[-] Transmission Error: {e}"
            )

            continue

        # ------------------------------------------
        # WAIT FOR RESPONSE
        # ------------------------------------------

        print(
            f"[RX 0x{TARGET_RX_ID:X}] Dispatched. Awaiting response from ECU..."
        )

        response = engine.receive(
            DEFAULT_TIMEOUT
        )

        # ------------------------------------------
        # RESPONSE VALIDATION
        # ------------------------------------------

        positive, message, data = evaluate_response(
            sid,
            payload,
            response
        )

        print(message)

        # ------------------------------------------
        # SESSION MANAGEMENT
        # ------------------------------------------

        if positive and sid == 0x10:

            session_type = payload[1]

            # Programming Session

            if session_type == 0x02:

                tester_present.start()

                print(
                    "[+] Programming Session Active"
                )

                print(
                    "[+] Background Keep-Alive Enabled"
                )

            # Extended Diagnostic Session

            elif session_type == 0x03:

                tester_present.start()

                print(
                    "[+] Extended Diagnostic Session Active"
                )

                print(
                    "[+] Background Keep-Alive Enabled"
                )

            # Default Session

            elif session_type == 0x01:

                tester_present.stop()

                print(
                    "[-] Returning To Default Session"
                )

                print(
                    "[-] Tester Present Stopped"
                )

        # ------------------------------------------
        # TIMEOUT CHECK
        # ------------------------------------------

        if response is None:

            print(
                "[!] ECU did not respond within timeout."
            )

            continue

        # ------------------------------------------
        # RAW RESPONSE DISPLAY  (spaced bytes, wrapped at 8 per line)
        # ------------------------------------------

        hex_tokens = [f"{b:02X}" for b in response]
        lines = [
            " ".join(hex_tokens[i:i + 8])
            for i in range(0, len(hex_tokens), 8)
        ]
        formatted = "\n   ".join(lines)

        print(
            f"<- Raw Response Received (Hex Stream):\n   {formatted}"
        )

        # ------------------------------------------
        # HUMAN READABLE DECODE
        # ------------------------------------------

        if positive:

            decoded_value = translator.decode(
                sid,
                target_id,
                data
            )

            print(
                "\n[DECODED HUMAN-READABLE METRIC]:"
            )

            print(
                f">> {decoded_value}"
            )


if __name__ == "__main__":
    main()