import time
import can
import isotp
import openpyxl
import os
import random
import threading

ECU_RX_ID = 0x7E0  # ECU listens here (Tester's Tx)
ECU_TX_ID = 0x7E8  # ECU responds here (Tester's Rx)
tester_present_seen = False

# Global state variables for the response switch
response_mode = 'p'  # Default to 'p' (Positive). Can be changed dynamically to 'n'
common_nrcs = [0x10, 0x11, 0x12, 0x13, 0x22, 0x31, 0x33, 0x7E]  # Common UDS NRC codes to randomize

# Pre-defined DTC Database Menu for selection
DTC_MENU = {
    1: {"code": "P0A80", "bytes": bytes.fromhex("0A 80 13"), "desc": "Replace Hybrid/EV Battery Pack"},
    2: {"code": "P0AA6", "bytes": bytes.fromhex("0A A6 4A"), "desc": "Hybrid Battery Voltage System Isolation Fault"},
    3: {"code": "P0A1F", "bytes": bytes.fromhex("0A 1F 11"), "desc": "Battery Energy Control Module Performance"},
    4: {"code": "P0C2F", "bytes": bytes.fromhex("0C 2F 00"), "desc": "Internal Control Module Drive Motor Control Performance"},
    5: {"code": "U0100", "bytes": bytes.fromhex("C1 00 87"), "desc": "Lost Communication With ECM/PCM"}
}

def setup_can_bus():
    try:
        return can.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

def fetch_mock_ecu_state(sid_val, sub_id_int):
    """Retrieves mock response data payload for matching IDs from ev_state_final.xlsx."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        full_path = os.path.join(parent_dir, 'config', 'ev_state_final.xlsx')
        wb = openpyxl.load_workbook(full_path, data_only=True)
        sheet = wb.active
    except Exception as e:
        print(f"[-] Error loading database matrix (ev_state_final.xlsx): {e}")
        return None

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[0] or row[2] is None: continue
        try:
            row_sid = int(str(row[0]), 16) if isinstance(row[0], str) else int(row[0])
            row_sub_id = int(str(row[2]), 16) if isinstance(row[2], str) else int(row[2])
            
            if row_sid == sid_val and row_sub_id == sub_id_int:
                return str(row[3]).strip() if row[3] is not None else "00"
        except ValueError: continue
    return None

def monitor_user_input():
    """Background thread function to listen for mode switch changes without blocking CAN."""
    global response_mode
    while True:
        try:
            user_input = input().strip().lower()
            if user_input == 'p':
                response_mode = 'p'
                print("\n[SWITCH] Switched to POSITIVE response mode.")
                print("------------------------------------------------")
            elif user_input == 'n':
                response_mode = 'n'
                print("\n[SWITCH] Switched to NEGATIVE (Fault) response mode with randomized NRCs.")
                print("------------------------------------------------")
        except (KeyboardInterrupt, EOFError):
            break

def main():
    global tester_present_seen, response_mode
    print("==================================================")
    print("    DYNAMIC MULTI-DTC INPUT CHANNELS EMULATOR     ")
    print(f"    Listening: 0x{ECU_RX_ID:X} & 0x7DF [Functional]   ")
    print("--------------------------------------------------")
    print("    RUNTIME SWITCH INTERFACE:                     ")
    print("    Type 'p' + Enter -> Force Positive Responses  ")
    print("    Type 'n' + Enter -> Force Randomized NRCs     ")
    print("==================================================")

    bus = setup_can_bus()
    if not bus: return

    stack_physical = isotp.CanStack(bus=bus, address=isotp.Address(rxid=ECU_RX_ID, txid=ECU_TX_ID), params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00})
    stack_functional = isotp.CanStack(bus=bus, address=isotp.Address(rxid=0x7DF, txid=ECU_TX_ID), params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00})

    print(f"[*] Network sockets linked. Awaiting diagnostic requests...\n")

    # Start the non-blocking keyboard input listener thread
    input_thread = threading.Thread(target=monitor_user_input, daemon=True)
    input_thread.start()

    try:
        while True:
            stack_physical.process()
            stack_functional.process()
            
            active_stack = None
            request_payload = None
            
            if stack_physical.available():
                active_stack = stack_physical
                request_payload = stack_physical.recv()
            elif stack_functional.available():
                active_stack = stack_functional
                request_payload = stack_functional.recv()
                
            if request_payload:
                sid = request_payload[0]

                # ALLOWED SIDs: Included 0x14 in the validation checklist
                if sid not in [0x10, 0x22, 0x3E, 0x19, 0x14]:
                    print(f"\n[!] Blocked Request Frame with unsupported SID: 0x{sid:02X}")
                    response_bytes = bytearray([0x7F, sid, 0x11])
                    active_stack.send(bytes(response_bytes))
                    while active_stack.transmitting():
                        stack_physical.process()
                        stack_functional.process()
                        time.sleep(0.005)
                    continue

                if sid == 0x22 and len(request_payload) >= 3:
                    sub_id_int = (request_payload[1] << 8) | request_payload[2]
                elif len(request_payload) >= 2:
                    sub_id_int = request_payload[1]
                else:
                    sub_id_int = 0x00

                if sid == 0x3E and sub_id_int == 0x80:
                     if not tester_present_seen:
                        print("\n[+] Tester Present Keep-Alive Started")
                        tester_present_seen = True
                     continue

                print(f"\n[!] Intercepted Request Frame: {request_payload.hex().upper()}")
                print(f"[*] Current Active Mode: {'POSITIVE' if response_mode == 'p' else 'NEGATIVE'}")
                response_bytes = bytearray()
                
                if response_mode == 'n':
                    # Automatically pick a randomized negative response code
                    nrc = random.choice(common_nrcs)
                    print(f"[-] Simulating Fault. Selected Random NRC: 0x{nrc:02X}")
                    response_bytes.extend([0x7F, sid, nrc])
                else:
                    response_bytes.append(sid + 0x40) # Positive Response ID generation
                    
                    if sid == 0x22:
                        response_bytes.extend([request_payload[1], request_payload[2]])
                    elif sid == 0x14:
                        pass 
                    elif len(request_payload) >= 2:
                        response_bytes.append(request_payload[1])
                    
                    if sid == 0x19:
                        print("\n--- AVAILABLE DTC SELECTION MENU ---")
                        for idx, info in DTC_MENU.items():
                            print(f"  [{idx}] {info['code']} -> {info['desc']}")
                        print("------------------------------------")
                        print("[*] Choose which DTCs to send back (e.g., enter '1' or '1,3,5').")
                        print("[*] Leave empty and press Enter to return a clear/empty status byte.")
                        
                        selection = input("Select Option(s): ").strip()
                        dtc_pool = bytearray()
                        
                        if selection:
                            # Split by commas and parse integer selections
                            choices = [c.strip() for c in selection.split(",")]
                            for choice in choices:
                                if choice.isdigit() and int(choice) in DTC_MENU:
                                    dtc_pool.extend(DTC_MENU[int(choice)]["bytes"])
                                else:
                                    print(f"  [!] Selection '{choice}' is invalid and was skipped.")
                        
                        if len(dtc_pool) > 0:
                            response_bytes.extend(dtc_pool)
                        else:
                            print("[-] No valid DTC choices selected. Returning default null placeholder byte.")
                            response_bytes.extend([0x00])

                    elif sid == 0x14:
                        print("[+] Executing diagnostic structural clear. Wiping error memory channels...")

                    elif sid == 0x22:
                        db_hex_val = fetch_mock_ecu_state(sid, sub_id_int)
                        if db_hex_val is not None:
                            hex_str = db_hex_val.replace("0x", "").strip()
                            if len(hex_str) % 2 != 0: hex_str = "0" + hex_str
                            response_bytes.extend(bytes.fromhex(hex_str))
                        else:
                            response_bytes = bytearray([0x7F, sid, 0x12])
                    elif sid == 0x10:
                        response_bytes.extend([0x00, 0x32, 0x01, 0xF4])  

                active_stack.send(bytes(response_bytes))
                while active_stack.transmitting():
                    stack_physical.process()
                    stack_functional.process()
                    time.sleep(0.005)
                print("[*] Response frame transmitted successfully.")
                
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[-] Shutting down ECU Emulator Node.")
    finally:
        try:
            stack_physical.close()
            stack_functional.close()
        except: pass

if __name__ == '__main__':
    main()