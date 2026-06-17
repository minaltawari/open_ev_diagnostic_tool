import openpyxl
import re

from config.file_paths import DECODE_FILE


class Translator:

    def __init__(self):

        self.workbook = openpyxl.load_workbook(
            DECODE_FILE,
            data_only=True
        )

        self.sheet = self.workbook.active

    def decode(
        self,
        sid,
        did,
        payload
    ):

        if sid == 0x19:

            if not payload:

                return "No DTC Present"

            return payload.hex().upper()

        for row in self.sheet.iter_rows(
                min_row=2,
                values_only=True):

            if not row[0]:
                continue

            text = str(row[0]).lower()

            match = re.search(
                r'\((.*?)\)',
                text
            )

            if match:

                try:

                    if int(
                        match.group(1),
                        16
                    ) == did:

                        return self.scale_value(
                            row,
                            payload
                        )

                except:
                    pass

        return payload.hex().upper()

    def scale_value(
        self,
        row,
        payload
    ):

        name = row[0]

        factor = row[3] or 1
        offset = row[4] or 0
        unit = row[5] or ""

        raw = int.from_bytes(
            payload,
            byteorder='big'
        )

        value = raw * factor + offset

        return f"{name}: {value} {unit}"
