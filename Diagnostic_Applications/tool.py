import time
import can
import isotp
import openpyxl
import re
import threading
import sys
import os
# ==============================================================================
# GLOBAL CONFIGURATION & RUNTIME DATA
# ==============================================================================
TARGET_TX_ID = 0x7E0  # Tester transmits to this ID
TARGET_RX_ID = 0x7E8  # Tester receives from this ID

tester_present_active = False
functional_stack = None  
bus_lock = threading.Lock() 

# ==============================================================================
# LAYER 1 & 3: HARDWARE INTERFACE & TRANSPORT SUBSYSTEM
# ==============================================================================
def init_hardware_bus():
    """Initializes the physical/virtual CAN network socket via UDP multicast."""
    try:
        return can.Bus(interface='udp_multicast', channel='224.0.0.1', port=5001)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

def init_transport_stack(bus, tx_id, rx_id):
    """Binds an ISO-TP physical connection network stack over the raw CAN bus."""
    addr = isotp.Address(rxid=rx_id, txid=tx_id)
    return isotp.CanStack(
        bus=bus, address=addr,
        params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
    )

def setup_functional_stack(bus):
    """Sets up a global functional diagnostic broadcast network link via 0x7DF."""
    addr = isotp.Address(rxid=TARGET_RX_ID, txid=0x7DF) 
    return isotp.CanStack(
        bus=bus, address=addr,
        params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
    )

def transmiting_data(stack, payload_bytes):
    """Handles low-level frame segmentation and transmission timing loop blocks."""
    with bus_lock:
        stack.send(payload_bytes)
        while stack.transmitting():
            stack.process()
            time.sleep(0.005)

def receiving_data(stack, timeout=15.0):
    """Monitors raw network buffers to reconstruct incoming frames into data buffers."""
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        stack.process()
        if stack.available():
            return stack.recv()
        time.sleep(0.01)
    return None

# ==============================================================================
# LAYER 4: UDS DIAGNOSTIC PROTOCOL LAYER
# ==============================================================================
def decode_nrc_code(nrc_byte):
    """Translates standard ISO 14229 UDS Negative Response Codes (NRC)."""
    nrc_dictionary = {
        0x10: "GeneralReject", 0x11: "ServiceNotSupported", 0x12: "SubFunctionNotSupported",
        0x13: "IncorrectMessageLengthOrInvalidFormat", 0x14: "ResponseTooLong",
        0x21: "BusyRepeatRequest", 0x22: "ConditionsNotCorrect", 0x24: "RequestSequenceError",
        0x25: "NoResponseFromSubnetComponent", 0x26: "FailurePreventsExecutionOfRequestedAction",
        0x31: "RequestOutOfRange", 0x33: "SecurityAccessDenied", 0x35: "InvalidKey",
        0x36: "ExceedNumberOfAttempts", 0x37: "RequiredTimeDelayNotExpired",
        0x70: "UploadDownloadNotAccepted", 0x71: "TransferDataSuspended",
        0x72: "GeneralProgrammingFailure", 0x73: "WrongBlockSequenceCounter",
        0x78: "RequestCorrectlyReceived-ResponsePending", 0x7E: "SubFunctionNotSupportedInActiveSession",
        0x7F: "ServiceNotSupportedInActiveSession"
    }
    return nrc_dictionary.get(nrc_byte, f"OEMReserved / UnknownFaultCode (0x{nrc_byte:02X})")

def evaluate_uds_response(sid, payload_bytes, response_bytes):
    """Evaluates whether a UDS response frame is Positive or Negative."""
    if not response_bytes:
        return False, "Diagnostic Session Timeout: Node failed to respond.", b""
        
    if response_bytes[0] == 0x7F:
        nrc_byte = response_bytes[2] if len(response_bytes) >= 3 else 0x00
        nrc_name = decode_nrc_code(nrc_byte)
        return False, f"[-] Negative Response Code (NRC) Frame Captured: 0x{nrc_byte:02X} -> [{nrc_name}]", b""
        
    expected_positive_sid = sid + 0x40
    if response_bytes[0] == expected_positive_sid:
        if sid in [0x22, 0x2E] and len(payload_bytes) >= 3:
            extracted_data = response_bytes[3:]
        elif sid == 0x14 and len(payload_bytes) >= 4:
            extracted_data = response_bytes[4:]
        elif len(payload_bytes) >= 2:
            extracted_data = response_bytes[2:]
        else:
            extracted_data = response_bytes[1:]
            
        return True, "[+] Positive Validation Frame Acknowledged!", extracted_data

    return False, "[-] Unexpected Protocol Frame Format Mismatch Error.", b""

def tester_present_thread_worker():
    """Broadcasts 3E 80 functionally over 0x7DF every 2 seconds to keep vehicle nodes active."""
    global tester_present_active, functional_stack
    while True:
        if tester_present_active and functional_stack:
            try:
                transmiting_data(functional_stack, bytes([0x3E, 0x80]))
            except Exception:
                pass
        time.sleep(2.0)

# ==============================================================================
# LAYER 5: DATA TRANSLATION SUBSYSTEM (PHYSICAL UNITS SCALE)
# ==============================================================================
def decode_did_value(sid_val, target_id_int, data_bytes):
    """Applies scaling and transformations to raw bytes. Bypasses Excel for SID 0x19."""
    if len(data_bytes) == 0:
        return "Command verification frame acknowledged successfully (No extra data payload)."

    if sid_val == 0x19:
        raw_hex = data_bytes.hex().upper()
        if not raw_hex or raw_hex == "00":
            return "Active Diagnostic Trouble Codes (DTCs): None / Empty List"
        formatted_dtcs = [raw_hex[i:i+6] for i in range(0, len(raw_hex), 6)]
        return f"Active Diagnostic Trouble Codes (DTCs): {', '.join(formatted_dtcs)}"

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        full_path = os.path.join(parent_dir, '2_Configuration_Data', 'decode_values.xlsx')
        wb = openpyxl.load_workbook(full_path, data_only=True)
        sheet = wb.active
    except Exception as e:
        return f"Error opening decode_values.xlsx at {full_path if 'full_path' in locals() else 'path'}: {e}"

    param_info = None
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[0]: continue
        row_string = str(row[0]).lower().strip()
        match = re.search(r'\((.*?)\)', row_string)
        if match:
            try:
                if int(match.group(1).strip(), 16) == target_id_int:
                    param_info = row
                    break
            except ValueError: continue
        else:
            try:
                if int(row_string, 16) == target_id_int:
                    param_info = row
                    break
            except ValueError: continue

    if not param_info:
        return f"Identifier Code {hex(target_id_int).upper()} Data Payload (Hex): {data_bytes.hex().upper()}"

    display_name = str(param_info[0]).split("(")[0].strip()
    formula_str = str(param_info[2]).lower() if param_info[2] else ""
    factor = param_info[3] if param_info[3] is not None else 1.0
    offset = param_info[4] if param_info[4] is not None else 0.0
    display_unit = str(param_info[5]).strip() if param_info[5] else ""

    try:
        if "string" in formula_str or "ascii" in formula_str:
            return f"{display_name}: {data_bytes.decode('ascii', errors='replace').strip()}"
        if "hex" in formula_str or display_unit.lower() == "hex":
            return f"{display_name}: {data_bytes.hex().upper()}"

        raw_val = 0
        for byte in data_bytes:
            raw_val = (raw_val << 8) | byte
            
        physical_val = (raw_val * float(factor)) + float(offset)
        physical_val = int(physical_val) if physical_val.is_integer() else round(physical_val, 2)
        return f"{display_name}: {physical_val} {display_unit}"
    except Exception as e:
        return f"Decoding Mismatch: {e} (Raw payload: {data_bytes.hex().upper()})"

# ==============================================================================
# MAIN EXECUTION ORCHESTRATOR
# ==============================================================================
def main():
    global tester_present_active, functional_stack
    
    print("==================================================")
    print("  STRICT SIDs (10, 22, 3E, 19, 14) DIAGNOSTIC TOOL")
    print("   [DIRECT TRANSMIT PORT MAP: 0x{_tx:X} -> 0x{_rx:X}]".format(_tx=TARGET_TX_ID, _rx=TARGET_RX_ID))
    print("==================================================")
    
    bus = init_hardware_bus()
    if not bus: return

    active_stack = init_transport_stack(bus, TARGET_TX_ID, TARGET_RX_ID)
    functional_stack = setup_functional_stack(bus)

    tp_thread = threading.Thread(target=tester_present_thread_worker, daemon=True)
    tp_thread.start()

    timeout_occurred = False

    while True:
        print("\n------------------------------------------------")
        req_hex = input("Enter Raw UDS Request Command (or 'Q' to quit): ").strip()
        if req_hex.lower() == 'q': break
        if not req_hex: continue
            
        try:
            payload_bytes = bytes.fromhex(req_hex.replace(" ", ""))
        except ValueError:
            print("[-] Invalid Hex format sequence.")
            continue

        sid = payload_bytes[0]
        
        # ALLOWED SIDs: Included 0x14 in the validation checklist
        if sid not in [0x10, 0x22, 0x3E, 0x19, 0x14]:
            print(f"[-] Unsupported Service Identifier: 0x{sid:02X}. Tool is restricted to 0x10, 0x22, 0x3E, 0x19, and 0x14.")
            continue

        if sid == 0x22 and len(payload_bytes) >= 3:
            sub_id_int = (payload_bytes[1] << 8) | payload_bytes[2]
        elif len(payload_bytes) >= 2:
            sub_id_int = payload_bytes[1]
        else:
            sub_id_int = 0x00

        try:
            while active_stack.available(): active_stack.recv()
        except: pass

        print(f"-> Transmitting directly to Target ECU (0x{TARGET_TX_ID:X})...")
        transmiting_data(active_stack, payload_bytes)
        
        if sid == 0x10 and sub_id_int in [0x02, 0x03]:
            print(f"[!] Session shifting tracked. Activating background Tester Present loop (0x7DF)...")
            tester_present_active = True
        elif sid == 0x10 and sub_id_int == 0x01:
            print("[-] Reverting to Default Session. Disengaging Functional Tester Present broadcast.")
            tester_present_active = False

        print("<- Dispatched. Awaiting response from ECU terminal...")
        response = receiving_data(active_stack, timeout=15.0)
        
        is_positive, description, stripped_payload = evaluate_uds_response(sid, payload_bytes, response)
        print(description)
        
        if "Timeout" in description:
            print("[!] Shutting down application entirely due to critical node unresponsiveness.")
            timeout_occurred = True
            break
        
        if response:
            print(f"<- Raw Response Received (Hex Stream): {response.hex().upper()}")
            if is_positive:
                print(f"\n[DECODED HUMAN-READABLE METRIC]:\n>> {decode_did_value(sid, sub_id_int, stripped_payload)}")
            elif sid == 0x10: 
                tester_present_active = False

    print("[*] De-allocating interfaces and shutting down CAN bus...")
    if bus:
        try:
            bus.shutdown()
        except Exception:
            pass
            
    if timeout_occurred:
        print("[+] Termination complete. Exiting process loop.")
        sys.exit(1)

if __name__ == '__main__':
    main()