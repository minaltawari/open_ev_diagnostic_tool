# ==========================================================
# ECU EMULATOR GUI
# ==========================================================
# Wraps the emulator logic from ecu.py in a GUI. Keeps ecu.py
# untouched and importable so the CLI tool still works standalone;
# this file just drives it with a Qt thread instead of a console
# loop, and replaces the runtime 'p'/'n' keypress and the DTC
# input() prompt with GUI controls.
# ==========================================================
import sys
import time
import random
import threading

import isotp

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QCheckBox, QTextEdit,
                             QLabel, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ecu import (
    ECU_RX_ID,
    ECU_TX_ID,
    DTC_MENU,
    common_nrcs,
    setup_can_bus,
    fetch_mock_ecu_state,
)


# ==========================================
# THREAD-SAFE SHARED CONFIG
# ==========================================
class EmulatorConfig:
    """Holds the GUI-controlled settings the worker thread reads from."""

    def __init__(self):
        self._lock = threading.Lock()
        self._response_mode = 'p'      # 'p' = positive, 'n' = negative
        self._selected_dtcs = set()    # set of DTC_MENU keys to include

    def get_response_mode(self):
        with self._lock:
            return self._response_mode

    def set_response_mode(self, mode):
        with self._lock:
            self._response_mode = mode

    def get_selected_dtcs(self):
        with self._lock:
            return set(self._selected_dtcs)

    def set_dtc_checked(self, dtc_id, checked):
        with self._lock:
            if checked:
                self._selected_dtcs.add(dtc_id)
            else:
                self._selected_dtcs.discard(dtc_id)


# ==========================================
# 🧵 BACKGROUND EMULATOR THREAD
# ==========================================
class ECUWorker(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, config: EmulatorConfig):
        super().__init__()
        self.config = config
        self.tester_present_seen = False
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        bus = setup_can_bus()
        if not bus:
            self.log_signal.emit("❌ Bus initialization failed.")
            return

        stack_physical = isotp.CanStack(
            bus=bus,
            address=isotp.Address(rxid=ECU_RX_ID, txid=ECU_TX_ID),
            params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
        )
        stack_functional = isotp.CanStack(
            bus=bus,
            address=isotp.Address(rxid=0x7DF, txid=ECU_TX_ID),
            params={'stmin': 10, 'blocksize': 8, 'tx_padding': 0x00}
        )

        self.log_signal.emit(
            f"✅ Network sockets linked. Listening: 0x{ECU_RX_ID:X} & 0x7DF [Functional]"
        )

        try:
            while not self._stop_event.is_set():
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
                    self._handle_request(
                        active_stack, stack_physical, stack_functional, request_payload
                    )

                time.sleep(0.01)

        except Exception as e:
            self.log_signal.emit(f"⚠️ System Exception: {str(e)}")

        finally:
            try:
                stack_physical.close()
                stack_functional.close()
            except Exception:
                pass
            self.log_signal.emit("🛑 ECU Emulator stopped.")

    # --------------------------------------------------
    def _transmit(self, active_stack, stack_physical, stack_functional, data):
        active_stack.send(data)
        while active_stack.transmitting():
            stack_physical.process()
            stack_functional.process()
            time.sleep(0.005)

    # --------------------------------------------------
    def _handle_request(self, active_stack, stack_physical, stack_functional, request_payload):
        sid = request_payload[0]

        # ------------------------------------------
        # SID VALIDATION
        # ------------------------------------------
        if sid not in [0x10, 0x22, 0x3E, 0x19, 0x14]:
            self.log_signal.emit(f"❌ Blocked Request Frame with unsupported SID: 0x{sid:02X}")
            response_bytes = bytearray([0x7F, sid, 0x11])
            self._transmit(active_stack, stack_physical, stack_functional, bytes(response_bytes))
            return

        if sid == 0x22 and len(request_payload) >= 3:
            sub_id_int = (request_payload[1] << 8) | request_payload[2]
        elif len(request_payload) >= 2:
            sub_id_int = request_payload[1]
        else:
            sub_id_int = 0x00

        # ------------------------------------------
        # TESTER PRESENT (silent keep-alive)
        # ------------------------------------------
        if sid == 0x3E and sub_id_int == 0x80:
            if not self.tester_present_seen:
                self.log_signal.emit("💓 Tester Present Keep-Alive Started")
                self.tester_present_seen = True
            return

        response_mode = self.config.get_response_mode()
        self.log_signal.emit(
            f"📨 Intercepted Request: {request_payload.hex().upper()} "
            f"| Mode: {'POSITIVE' if response_mode == 'p' else 'NEGATIVE'}"
        )

        response_bytes = bytearray()

        # ------------------------------------------
        # NEGATIVE MODE
        # ------------------------------------------
        if response_mode == 'n':
            nrc = random.choice(common_nrcs)
            self.log_signal.emit(f"⚠️ Simulating Fault. Selected Random NRC: 0x{nrc:02X}")
            response_bytes.extend([0x7F, sid, nrc])

        # ------------------------------------------
        # POSITIVE MODE
        # ------------------------------------------
        else:
            response_bytes.append(sid + 0x40)

            if sid == 0x22:
                response_bytes.extend([request_payload[1], request_payload[2]])
            elif sid == 0x14:
                pass
            elif len(request_payload) >= 2:
                response_bytes.append(request_payload[1])

            if sid == 0x19:
                selected_ids = self.config.get_selected_dtcs()
                dtc_pool = bytearray()
                sent_codes = []

                for dtc_id in selected_ids:
                    if dtc_id in DTC_MENU:
                        dtc_pool.extend(DTC_MENU[dtc_id]["bytes"])
                        sent_codes.append(DTC_MENU[dtc_id]["code"])

                if dtc_pool:
                    response_bytes.extend(dtc_pool)
                    self.log_signal.emit(f"📋 Sending checked DTCs: {', '.join(sent_codes)}")
                else:
                    response_bytes.extend([0x00])
                    self.log_signal.emit("📋 No DTCs checked. Returning empty status byte.")

            elif sid == 0x14:
                self.log_signal.emit("🧹 Executing diagnostic structural clear. Wiping error memory channels...")

            elif sid == 0x22:
                db_hex_val = fetch_mock_ecu_state(sid, sub_id_int)
                if db_hex_val is not None:
                    hex_str = db_hex_val.replace("0x", "").strip()
                    if len(hex_str) % 2 != 0:
                        hex_str = "0" + hex_str
                    response_bytes.extend(bytes.fromhex(hex_str))
                else:
                    response_bytes = bytearray([0x7F, sid, 0x12])

            elif sid == 0x10:
                response_bytes.extend([0x00, 0x32, 0x01, 0xF4])

        self._transmit(active_stack, stack_physical, stack_functional, bytes(response_bytes))
        self.log_signal.emit(f"📤 Response transmitted: {bytes(response_bytes).hex().upper()}")


# ==========================================
# 🖥️ MAIN GUI CLASS
# ==========================================
class ECUEmulatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EV Mock ECU Emulator")
        self.resize(850, 500)

        self.config = EmulatorConfig()
        self.worker = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)

        main_layout.addLayout(self.left_layout, stretch=2)
        main_layout.addWidget(divider)
        main_layout.addLayout(self.right_layout, stretch=1)

        self.build_left_side()
        self.build_right_side()

    # --------------------------------------------------
    def build_left_side(self):
        title = QLabel("<b>🚗 Mock ECU Emulator</b>")
        title.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(title)

        self.left_layout.addWidget(
            QLabel(f"Listening: 0x{ECU_RX_ID:X} (physical) & 0x7DF (functional)")
        )

        self.start_btn = QPushButton("▶ Start Emulator")
        self.start_btn.setStyleSheet("background-color: #107C10; color: white; font-weight: bold; padding: 5px;")
        self.start_btn.clicked.connect(self.start_emulator)
        self.left_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ Stop Emulator")
        self.stop_btn.setStyleSheet("background-color: #B00020; color: white; font-weight: bold; padding: 5px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_emulator)
        self.left_layout.addWidget(self.stop_btn)

        self.left_layout.addWidget(QLabel("Bus Logs:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.left_layout.addWidget(self.log_display)

        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.clicked.connect(self.log_display.clear)
        self.left_layout.addWidget(self.clear_btn)

    # --------------------------------------------------
    def build_right_side(self):
        title = QLabel("<b>⚙️ Response Settings</b>")
        title.setAlignment(Qt.AlignCenter)
        self.right_layout.addWidget(title)

        # ---- Positive / Negative switch ----
        self.right_layout.addWidget(QLabel("Response Mode:"))
        self.mode_switch = QPushButton("✅  POSITIVE")
        self.mode_switch.setCheckable(True)
        self.mode_switch.setChecked(False)  # unchecked = positive
        self.mode_switch.setStyleSheet(
            "background-color: #107C10; color: white; font-weight: bold; padding: 8px;"
        )
        self.mode_switch.clicked.connect(self.toggle_response_mode)
        self.right_layout.addWidget(self.mode_switch)

        self.right_layout.addWidget(QLabel(""))  # spacer

        # ---- DTC checkboxes ----
        self.right_layout.addWidget(QLabel("DTCs to report on SID 0x19 (check to include):"))
        self.dtc_checkboxes = {}
        for dtc_id, info in DTC_MENU.items():
            checkbox = QCheckBox(f"{info['code']} \u2014 {info['desc']}")
            checkbox.stateChanged.connect(
                lambda state, did=dtc_id: self.config.set_dtc_checked(did, state == Qt.Checked)
            )
            self.right_layout.addWidget(checkbox)
            self.dtc_checkboxes[dtc_id] = checkbox

        self.right_layout.addStretch()

    # --------------------------------------------------
    def toggle_response_mode(self):
        if self.mode_switch.isChecked():
            self.config.set_response_mode('n')
            self.mode_switch.setText("⚠️  NEGATIVE")
            self.mode_switch.setStyleSheet(
                "background-color: #B00020; color: white; font-weight: bold; padding: 8px;"
            )
        else:
            self.config.set_response_mode('p')
            self.mode_switch.setText("✅  POSITIVE")
            self.mode_switch.setStyleSheet(
                "background-color: #107C10; color: white; font-weight: bold; padding: 8px;"
            )

    # --------------------------------------------------
    def start_emulator(self):
        if self.worker and self.worker.isRunning():
            return

        self.worker = ECUWorker(self.config)
        self.worker.log_signal.connect(self.append_log)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_emulator(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(2000)

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def append_log(self, message):
        self.log_display.append(message)

    # --------------------------------------------------
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ECUEmulatorGUI()
    window.show()
    sys.exit(app.exec_())
