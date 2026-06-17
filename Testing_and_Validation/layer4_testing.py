# ==============================================================================
# LAYER 4: UDS DIAGNOSTIC PROTOCOL LAYER (VALIDATION & SERVICE STATE CONTROL)
# ==============================================================================
def decode_nrc_code(nrc_byte):
    """Translates standard ISO 14229 UDS Negative Response Codes (NRC)."""
    nrc_dictionary = {
        0x10: "GeneralReject",
        0x11: "ServiceNotSupported",
        0x12: "SubFunctionNotSupported",
        0x13: "IncorrectMessageLengthOrInvalidFormat",
        0x14: "ResponseTooLong",
        0x21: "BusyRepeatRequest",
        0x22: "ConditionsNotCorrect",
        0x24: "RequestSequenceError",
        0x25: "NoResponseFromSubnetComponent",
        0x26: "FailurePreventsExecutionOfRequestedAction",
        0x31: "RequestOutOfRange",
        0x33: "SecurityAccessDenied",
        0x35: "InvalidKey",
        0x36: "ExceedNumberOfAttempts",
        0x37: "RequiredTimeDelayNotExpired",
        0x70: "UploadDownloadNotAccepted",
        0x71: "TransferDataSuspended",
        0x72: "GeneralProgrammingFailure",
        0x73: "WrongBlockSequenceCounter",
        0x78: "RequestCorrectlyReceived-ResponsePending",
        0x7E: "SubFunctionNotSupportedInActiveSession",
        0x7F: "ServiceNotSupportedInActiveSession"
    }
    return nrc_dictionary.get(nrc_byte, f"OEMReserved / UnknownFaultCode (0x{nrc_byte:02X})")

def evaluate_uds_response(sid, payload_bytes, response_bytes):
    """
    Evaluates whether a UDS response frame is Positive or Negative.
    Strips protocol overhead from positive frames to reveal the raw payload.
    
    Inputs:
        sid (int): Request Service ID byte.
        payload_bytes (bytes): Original requested payload array.
        response_bytes (bytes): Raw frame received back from target node.
        
    Outputs:
        tuple: (status_bool, description_msg, target_extracted_payload)
    """
    if not response_bytes:
        return False, "Diagnostic Session Timeout: Node failed to respond.", b""
        
    # Check for UDS Negative Response Service ID (0x7F)
    if response_bytes[0] == 0x7F:
        nrc_byte = response_bytes[2] if len(response_bytes) >= 3 else 0x00
        nrc_name = decode_nrc_code(nrc_byte)
        status_msg = f"[-] Negative Response Code (NRC) Frame Captured: 0x{nrc_byte:02X} -> [{nrc_name}]"
        return False, status_msg, b""
        
    # Check for valid Service ID pairing (Request SID + 0x40)
    expected_positive_sid = sid + 0x40
    if response_bytes[0] == expected_positive_sid:
        # Custom overhead slicing depends on target SID signature formats
        if sid in [0x22, 0x2E] and len(payload_bytes) >= 3:
            extracted_data = response_bytes[3:]  # Strips SID, DID_Hi, DID_Lo
        elif sid == 0x14 and len(payload_bytes) >= 4:
            extracted_data = response_bytes[4:]  # Strips SID, Memory/Clear bounds
        elif len(payload_bytes) >= 2:
            extracted_data = response_bytes[2:]  # Strips SID, SubFunction
        else:
            extracted_data = response_bytes[1:]  # Strips SID byte only
            
        return True, "[+] Positive Validation Frame Acknowledged!", extracted_data

    return False, "[-] Unexpected Protocol Frame Format Mismatch Error.", b""

def tester_present_thread_worker():
    """Broadcasts 3E 80 functionally over 0x7DF every 2 seconds to keep vehicle nodes active."""
    global tester_present_active, functional_stack
    while True:
        if tester_present_active and functional_stack:
            keep_alive_payload = bytes([0x3E, 0x80])
            try:
                transmiting_data(functional_stack, keep_alive_payload)
            except Exception:
                pass
        time.sleep(2.0)
while True:

    print("\n========================================")
    print("LAYER 4 REQUEST + RESPONSE TEST")
    print("========================================")

    req_hex = input(
        "\nEnter Request (or Q to quit): "
    ).strip()

    if req_hex.lower() == "q":
        break

    try:
        payload_bytes = bytes.fromhex(
            req_hex.replace(" ", "")
        )
    except ValueError:
        print("Invalid request hex")
        continue

    sid = payload_bytes[0]

    # ---------------------------
    # REQUEST SIDE
    # ---------------------------

    if sid in [0x22, 0x2E] and len(payload_bytes) >= 3:

        sub_id_int = (
            (payload_bytes[1] << 8)
            | payload_bytes[2]
        )

    elif sid == 0x14 and len(payload_bytes) >= 4:

        sub_id_int = (
            (payload_bytes[1] << 16)
            | (payload_bytes[2] << 8)
            | payload_bytes[3]
        )

    elif len(payload_bytes) >= 2:

        sub_id_int = payload_bytes[1]

    else:

        sub_id_int = 0x00

    print("\n----- REQUEST OUTPUT -----")

    print(f"SID : 0x{sid:02X}")

    if sid == 0x22:
        print(f"DID : 0x{sub_id_int:04X}")

    elif sid == 0x2E:
        print(f"DID : 0x{sub_id_int:04X}")

    else:
        print(f"SUB_ID : 0x{sub_id_int:X}")

    # ---------------------------
    # RESPONSE INPUT
    # ---------------------------

    resp_hex = input(
        "\nEnter ECU Response : "
    ).strip()

    try:
        response_bytes = bytes.fromhex(
            resp_hex.replace(" ", "")
        )
    except ValueError:
        print("Invalid response hex")
        continue

    # ---------------------------
    # RESPONSE SIDE
    # ---------------------------

    is_positive, description, stripped_payload = (
        evaluate_uds_response(
            sid,
            payload_bytes,
            response_bytes
        )
    )

    print("\n----- RESPONSE OUTPUT -----")

    print("Status:")
    print(is_positive)

    print("\nDescription:")
    print(description)

    print("\nSID:")
    print(f"0x{sid:02X}")

    if sid in [0x22, 0x2E]:
        print("DID:")
        print(f"0x{sub_id_int:04X}")

    print("\nPayload To Layer 5:")
    print(stripped_payload.hex().upper())

    print("\n========================================")