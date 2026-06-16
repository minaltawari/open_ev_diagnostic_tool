import time
import can
import isotp
import openpyxl

ECU_RX_ID = 0x7E0  # ECU listens here (Tester's Tx)
ECU_TX_ID = 0x7E8  # ECU responds here (Tester's Rx)

def setup_can_bus():
    try:
        return can.Bus(interface='udp_multicast', channel='224.0.0.1', port=5001)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

def fetch_mock_ecu_state(sid_val, sub_id_int):
    """Retrieves mock response data payload for matching IDs from ev_state_final.xlsx."""
    try:
        wb = openpyxl.load_workbook('ev_state_final.xlsx', data_only=True)
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

def main():
    print("==================================================")
    print("    DYNAMIC MULTI-DTC INPUT CHANNELS EMULATOR     ")
    print(f"    Listening: 0x{ECU_RX_ID:X} & 0x7DF [Functional]   ")
    print("==================================================")

    bus = setup_can_bus()
    if not bus: return

    stack_physical = isotp.CanStack(bus=bus, address=isotp.Address(rxid=ECU_RX_ID, txid=ECU_TX_ID), params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00})
    stack_functional = isotp.CanStack(bus=bus, address=isotp.Address(rxid=0x7DF, txid=ECU_TX_ID), params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00})

    print(f"[*] Network sockets linked. Awaiting diagnostic requests...")

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

                if sid not in [0x10, 0x22, 0x3E, 0x19]:
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
                    continue

                print(f"\n[!] Intercepted Request Frame: {request_payload.hex().upper()}")
                response_bytes = bytearray()

                print("------------------------------------------------")
                user_choice = input("Select response behavior -> [P] Positive  [N] Negative (Fault): ").strip().lower()
                
                if user_choice == 'n':
                    nrc_input = input("Enter Hex NRC Fault Code (Default 0x22): ").strip()
                    nrc = int(nrc_input, 16) if nrc_input else 0x22
                    response_bytes.extend([0x7F, sid, nrc])
                else:
                    response_bytes.append(sid + 0x40)
                    if sid == 0x22:
                        response_bytes.extend([request_payload[1], request_payload[2]])
                    elif len(request_payload) >= 2:
                        response_bytes.append(request_payload[1])
                    
                    if sid == 0x19:
                        print("[*] Enter DTC hex payloads (e.g., 'A9 00 11' or '0A 01 12').")
                        print("[*] Press Enter on an empty line when you are done adding codes.")
                        
                        dtc_pool = bytearray()
                        count = 1
                        while True:
                            dtc_item = input(f"  -> Enter DTC #{count} (or leave empty to finish): ").strip()
                            if not dtc_item:
                                break
                            try:
                                hex_str = dtc_item.replace(" ", "").strip()
                                if len(hex_str) % 2 != 0: hex_str = "0" + hex_str
                                dtc_pool.extend(bytes.fromhex(hex_str))
                                count += 1
                            except ValueError:
                                print("  [-] Invalid Hex formatting. Try entering this code again.")
                        
                        if len(dtc_pool) > 0:
                            response_bytes.extend(dtc_pool)
                        else:
                            print("[-] No DTCs entered. Transmitting single null data placeholder byte.")
                            response_bytes.extend([0x00])

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