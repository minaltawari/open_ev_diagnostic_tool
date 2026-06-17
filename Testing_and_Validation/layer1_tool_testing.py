import can
import sys

def init_hardware_bus():
    try:
        # Layer 1: Hardware Abstraction over virtual UDP multicast
        return can.Bus(interface='udp_multicast', channel='224.0.0.1', port=5001)
    except Exception as e:
        print(f"[-] Bus initialization failed: {e}")
        return None

if __name__ == "__main__":
    print("=== [TOOL] Testing Bus Setup ===")
    bus = init_hardware_bus()
    
    if bus is not None:
        print("[+] Tool Bus opened successfully!")
        
        # Test frame (ID: 0x7DF is the typical functional address for OBD-II/UDS diagnostics)
        msg = can.Message(
            arbitration_id=0x7DF, 
            data=[0x11, 0x22, 0x33], 
            is_extended_id=False
        )
        
        try:
            print("-> Transmitting Layer 1 test message onto virtual bus...")
            bus.send(msg)
            print("[+] Message sent successfully!")
        except Exception as e:
            print(f"[-] Transmission failed: {e}")
        finally:
            bus.shutdown()
            print("[*] Bus shut down safely.")