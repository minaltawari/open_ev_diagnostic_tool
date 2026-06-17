# ==============================================================================
# LAYER 5: TRANSLATIONS & DATA TRANSLATION SUBSYSTEM
# ==============================================================================
import openpyxl
import re

def process_user_request(raw_command):
    """
    Receives raw UDS command from Layer 6.
    Cleans and converts it into bytes for Layer 4.
    """

    try:
        cleaned_command = raw_command.strip()
        cleaned_command = cleaned_command.replace(" ", "")

        payload_bytes = bytes.fromhex(cleaned_command)

        return True, payload_bytes

    except Exception as e:
        return False, str(e)




def decode_did_value(target_id_int, data_bytes):
    """Applies scaling, bitwise parsing, and algebraic transformations to raw bytes."""
    if len(data_bytes) == 0:
        return "Command verification frame acknowledged successfully (No extra data payload)."

    try:
        wb = openpyxl.load_workbook(r'.\2_Configuration_Data\decode_values.xlsx', data_only=True)
        sheet = wb.active
    except Exception as e:
        return f"Error opening decode_values.xlsx: {e}"

    param_info = None
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[0]: 
            continue
        row_string = str(row[0]).lower().strip()
        match = re.search(r'\((.*?)\)', row_string)
        if match:
            try:
                excel_id_int = int(match.group(1).strip(), 16)
                if excel_id_int == target_id_int:
                    param_info = row
                    break
            except ValueError: 
                continue
        else:
            try:
                if int(row_string, 16) == target_id_int:
                    param_info = row
                    break
            except ValueError: 
                continue

    if not param_info:
        return f"Identifier Code {hex(target_id_int).upper()} Data Payload (Hex): {data_bytes.hex().upper()}"

    excel_parameter_column = param_info[0] 
    formula_str = str(param_info[2]).lower() if param_info[2] else ""
    factor = param_info[3] if param_info[3] is not None else 1.0
    offset = param_info[4] if param_info[4] is not None else 0.0
    unit = param_info[5]

    display_name = excel_parameter_column.split("(")[0].strip()
    display_unit = str(unit).strip() if unit else ""

    try:
        if "string" in formula_str or "ascii" in formula_str:
            return f"{display_name}: {data_bytes.decode('ascii', errors='replace').strip()}"
        
        if "hex" in formula_str or display_unit.lower() == "hex":
            return f"{display_name}: {data_bytes.hex().upper()}"

        raw_val = 0
        for byte in data_bytes:
            raw_val = (raw_val << 8) | byte
            
        physical_val = (raw_val * float(factor)) + float(offset)
        if isinstance(physical_val, float) and physical_val.is_integer():
            physical_val = int(physical_val)
        else:
            physical_val = round(physical_val, 2)

        return f"{display_name}: {physical_val} {display_unit}"
    except Exception as e:
        return f"Decoding Mismatch: {e} (Raw payload: {data_bytes.hex().upper()})"

if __name__ == "__main__":

    print("====================================")
    print("      LAYER 5 STANDALONE TEST")
    print("====================================")

    # -----------------------------
    # REQUEST SIDE TEST
    # -----------------------------
    print("\n[REQUEST PATH]")


    raw_request = input(
        "\nEnter UDS Command from Layer 6: "
    )

    status, payload = process_user_request(raw_request)

    if status:
        print("\nOutput sent to Layer 4:")
        print(payload)
        print("HEX:", payload.hex().upper())
    else:
        print("\nError:")
        print(payload)

    # -----------------------------
    # RESPONSE SIDE TEST
    # -----------------------------
    print("\n------------------------------------")
    print("[RESPONSE PATH]")


    try:
        did_input = input(
            "\nEnter DID/Sub-ID (Hex): "
        )

        target_id_int = int(did_input, 16)

        response_input = input(
            "Enter Payload from Layer 4 (Hex): "
        )

        data_bytes = bytes.fromhex(
            response_input.replace(" ", "")
        )

        result = decode_did_value(
            target_id_int,
            data_bytes
        )

        print("\nOutput sent to Layer 6:")
        print(result)

    except Exception as e:
        print(f"\nError: {e}")