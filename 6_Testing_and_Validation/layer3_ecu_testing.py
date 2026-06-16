import time
import can
import isotp

def setup_can_bus():
    try:
        return can.Bus(interface='udp_multicast', channel='224.0.0.1', port=5001)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

def transmiting_data(stack, payload_bytes):
    stack.send(payload_bytes)
    while stack.transmitting():
        stack.process()
        time.sleep(0.005)

def receiving_data(stack):
    while True:
        stack.process()
        if stack.available():
            return stack.recv()
        time.sleep(0.01)

def main():
    # Fixed Single ECU Configuration (Standard UDS engine/BMS IDs)
    rx_id = 0x7E0
    tx_id = 0x7E8

    print("==================================================")
    print("        SYSTEM TEST: SINGLE VIRTUAL ECU           ")
    print(f"    Listening on RX: 0x{rx_id:X} | Responding on TX: 0x{tx_id:X}")
    print("==================================================")

    bus = setup_can_bus()
    if not bus: 
        return

    # Link the physical ISO-TP network communication stack
    addr_physical = isotp.Address(rxid=rx_id, txid=tx_id)
    stack_physical = isotp.CanStack(
        bus=bus, 
        address=addr_physical, 
        params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
    )

    print(f"[*] ISO-TP Stack Online. Awaiting diagnostic requests...")

    try:
        while True:
            # 1. Wait infinitely for incoming packet strings from the tool
            request_payload = receiving_data(stack_physical)
            
            print("\n" + "="*50)
            print("[!] Request Received From Tool Side!")
            print(f"    Received Raw Bytes: {request_payload}")
            print(f"    Received Hex Stream: {request_payload.hex().upper()}")
            print("="*50)
            
            # 2. Prompt operator for manual return payload data bytes
            print("\n------------------------------------------------")
            user_input = input("Enter ECU Response bytes literal (e.g., b'\\x62\\xF1\\x90\\x01'): ").strip()
            
            try:
                response_bytes = eval(user_input)
                if not isinstance(response_bytes, bytes):
                    raise TypeError("Input must be a valid bytes object.")
            except Exception as e:
                print(f"[-] Format error ({e}). Defaulting to error payload.")
                response_bytes = b"\x7F" + bytes([request_payload[0]]) + b"\x22"
            
            # 3. Send response payload back down the stack architecture
            print(f"-> Processing stack transmission loop...")
            transmiting_data(stack_physical, response_bytes)
            print("[*] Output buffer cleared. Transaction complete.")

    except KeyboardInterrupt:
        print("\n[-] Shutting down ECU node link.")
    finally:
        try:
            stack_physical.close()
        except:
            pass

if __name__ == '__main__':
    main()