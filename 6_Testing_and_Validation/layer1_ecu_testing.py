import can
import time

def setup_can_bus():
    try:
        # Layer 1: Hardware Abstraction over virtual UDP multicast
        return can.Bus(interface='udp_multicast', channel='224.0.0.1', port=5001)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

if __name__ == "__main__":
    print("=== [ECU] Testing Bus Setup ===")
    bus = setup_can_bus()
    
    if bus is not None:
        print("[*] Layer 1 Online. Waiting for multicast packets...")
        try:
            # Block and wait indefinitely for a message
            msg = bus.recv(timeout=None)
            
            if msg is not None:
                print("\n[+] COMMUNICATION SUCCESSFUL! Message received:")
                print(f"    From CAN ID: 0x{msg.arbitration_id:X}")
                print(f"    Data (Hex):  {msg.data.hex().upper()}")
                print(f"    Timestamp:   {time.strftime('%H:%M:%S')}")
                
        except KeyboardInterrupt:
            print("\n[-] Stopped by user.")
        finally:
            bus.shutdown()
            print("[*] Bus shut down safely.")