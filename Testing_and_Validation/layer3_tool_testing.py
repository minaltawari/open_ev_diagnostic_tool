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
    print("==================================================")
    print("         SYSTEM TEST: SINGLE DIAGNOSTIC TOOL       ")
    print("==================================================")
    
    bus = setup_can_bus()
    if not bus:
        return

    # Initialize a single tracking network stack configured matching our ECU target
    # Tool Tx = ECU Rx (0x7E0), Tool Rx = ECU Tx (0x7E8)
    addr = isotp.Address(rxid=0x7E8, txid=0x7E0)
    active_stack = isotp.CanStack(
        bus=bus,
        address=addr,
        params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
    )

    while True:
        print("\n------------------------------------------------")
        user_input = input("Enter Request Command bytes literal (e.g., b'\\x22\\xF1\\x90') or 'Q': ").strip()
        
        if user_input.lower() == 'q':
            break
        if not user_input:
            continue
            
        try:
            request_bytes = eval(user_input)
            if not isinstance(request_bytes, bytes):
                raise TypeError("Input must be a valid bytes object.")
        except Exception as e:
            print(f"[-] Format Error: {e}")
            continue

        # Flush matching queue channel before sending
        try:
            while active_stack.available(): active_stack.recv()
        except: pass

        # Transmit out utilizing modular pipeline execution logic
        print("-> Sending frames to ECU target address 0x7E0...")
        transmiting_data(active_stack, request_bytes)
        
        # Block infinitely waiting for the targeted ECU's interactive reply frame
        print("<- Dispatched. Awaiting response loop echo directly from ECU...")
        response = receiving_data(active_stack)
        
        print("\n" + "="*50)
        print("[+] FINAL TRANSACTION RECORDED AT TOOL SIDE!")
        print(f"    Raw Bytes Representation : {response}")
        print(f"    Raw Hex Stream           : {response.hex().upper()}")
        print("="*50)

    print("\nClosing tool network socket links...")
    try:
        active_stack.close()
    except:
        pass

if __name__ == '__main__':
    main()