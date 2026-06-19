# ==========================================================
# DIAGNOSTIC GUI APPLICATION
# ==========================================================
import os
import sys

# Force Python to look at the workspace root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QLineEdit, QTextEdit,
                             QLabel, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.can_interface import init_hardware_bus

from core.transport_layer import (
    create_physical_stack,
    create_functional_stack
)

from core.diagnostic_engine import DiagnosticEngine

from core.uds_layer import evaluate_response

from core.translator import Translator

from core.tester_present import TesterPresentManager

from config.user_config import *


# ==========================================
# 🧵 THE BACKGROUND WORKER THREAD
# ==========================================
class UDSWorker(QThread):
    """
    Sends a raw UDS payload through the diagnostic engine and reports
    the outcome back to the GUI. Mirrors the send/receive/evaluate/decode
    flow used by the CLI tool (main.py).
    """
    result_ready = pyqtSignal(dict)

    def __init__(self, engine, translator, sid, target_id, payload):
        super().__init__()
        self.engine = engine
        self.translator = translator
        self.sid = sid
        self.target_id = target_id
        self.payload = payload

    def run(self):
        """This runs entirely in the background so the GUI doesn't freeze."""
        result = {
            "sid": self.sid,
            "payload": self.payload,
            "positive": False,
            "message": "",
            "response": None,
            "decoded": None,
        }

        try:
            self.engine.send(self.payload)
            response = self.engine.receive(DEFAULT_TIMEOUT)
            result["response"] = response

            positive, message, data = evaluate_response(
                self.sid, self.payload, response
            )
            result["positive"] = positive
            result["message"] = message

            if positive and data is not None:
                result["decoded"] = self.translator.decode(
                    self.sid, self.target_id, data
                )

        except Exception as e:
            result["message"] = f"⚠️ System Exception: {str(e)}"

        self.result_ready.emit(result)


# ==========================================
# 🖥️ THE MAIN GUI CLASS
# ==========================================
class DiagnosticsGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EV Diagnostics Tool")
        self.resize(850, 500)

        self.bus = None
        self.engine = None
        self.translator = None
        self.tester_present = None

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

        self.init_hardware()

    # --------------------------------------------------
    # HARDWARE / ENGINE INITIALIZATION
    # --------------------------------------------------
    def init_hardware(self):
        self.bus = init_hardware_bus()

        if not self.bus:
            self.log_display.append("❌ Failed to initialize CAN Bus. Sending is disabled.")
            self.send_btn.setEnabled(False)
            return

        physical_stack = create_physical_stack(self.bus, TARGET_TX_ID, TARGET_RX_ID)
        create_functional_stack(self.bus, TARGET_RX_ID)  # reserved for functional addressing

        self.engine = DiagnosticEngine(physical_stack)
        self.translator = Translator()
        self.tester_present = TesterPresentManager(self.engine)

        self.log_display.append(
            f"✅ CAN Bus initialized. Target: 0x{TARGET_TX_ID:X} -> 0x{TARGET_RX_ID:X}"
        )
        self.log_display.append("-" * 40)

    # --------------------------------------------------
    # UI BUILD
    # --------------------------------------------------
    def build_left_side(self):
        title = QLabel("<b>🖥️ Diagnostic Tester Tool</b>")
        title.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(title)

        self.left_layout.addWidget(QLabel("Enter Raw UDS Request (hex bytes):"))

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("e.g. 10 03   or   22 02 01")
        self.command_input.returnPressed.connect(self.send_uds_request)
        self.left_layout.addWidget(self.command_input)

        sid_hint = ", ".join(f"0x{s:02X}" for s in sorted(SUPPORTED_SIDS))
        hint_label = QLabel(f"Supported SIDs: {sid_hint}")
        hint_label.setStyleSheet("color: gray; font-size: 10px;")
        self.left_layout.addWidget(hint_label)

        self.send_btn = QPushButton("Send Request")
        self.send_btn.setStyleSheet("background-color: #0078D7; color: white; font-weight: bold; padding: 5px;")
        self.left_layout.addWidget(self.send_btn)
        self.send_btn.clicked.connect(self.send_uds_request)

        self.left_layout.addWidget(QLabel("Bus Logs:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.left_layout.addWidget(self.log_display)

        self.clear_btn = QPushButton("Clear Logs")
        self.left_layout.addWidget(self.clear_btn)
        self.clear_btn.clicked.connect(self.clear_logs)

    def build_right_side(self):
        title = QLabel("<b>🔌 Session Status</b>")
        title.setAlignment(Qt.AlignCenter)
        self.right_layout.addWidget(title)

        self.session_label = QLabel("Session: Default")
        self.right_layout.addWidget(self.session_label)

        self.tester_present_label = QLabel("Tester Present: Inactive")
        self.right_layout.addWidget(self.tester_present_label)

        self.right_layout.addWidget(QLabel(f"TX ID: 0x{TARGET_TX_ID:X}"))
        self.right_layout.addWidget(QLabel(f"RX ID: 0x{TARGET_RX_ID:X}"))

        self.right_layout.addStretch()

    # --------------------------------------------------
    # ACTIONS
    # --------------------------------------------------
    def clear_logs(self):
        self.log_display.clear()

    def send_uds_request(self):
        if not self.engine:
            self.log_display.append("❌ Engine not initialized. Cannot send.")
            return

        raw_text = self.command_input.text().strip()
        if not raw_text:
            return

        # ------------------------------------------
        # HEX VALIDATION
        # ------------------------------------------
        try:
            payload = bytes.fromhex(raw_text.replace(" ", ""))
        except ValueError:
            self.log_display.append("❌ Invalid Hex format sequence.")
            return

        if not payload:
            self.log_display.append("❌ Empty payload.")
            return

        sid = payload[0]

        # ------------------------------------------
        # SID VALIDATION
        # ------------------------------------------
        if sid not in SUPPORTED_SIDS:
            self.log_display.append(f"❌ Unsupported Service Identifier: 0x{sid:02X}")
            return

        # ------------------------------------------
        # EXTRACT DID / SUBFUNCTION
        # ------------------------------------------
        if sid == 0x22 and len(payload) >= 3:
            target_id = (payload[1] << 8) | payload[2]
        elif len(payload) >= 2:
            target_id = payload[1]
        else:
            target_id = 0x00

        hex_str = " ".join(f"{b:02X}" for b in payload)
        self.log_display.append(f"<b>[TX]</b> Sending: <i>{hex_str}</i>...")

        # Disable the send button so the user doesn't spam it
        self.send_btn.setEnabled(False)

        # Create and start the background thread
        self.worker = UDSWorker(self.engine, self.translator, sid, target_id, payload)
        self.worker.result_ready.connect(self.handle_worker_result)
        self.worker.start()

    def handle_worker_result(self, result):
        """This Slot receives the signal from the Worker when the request finishes."""
        sid = result["sid"]
        payload = result["payload"]
        positive = result["positive"]
        message = result["message"]
        response = result["response"]
        decoded = result["decoded"]

        self.log_display.append(f"<b>[RX]</b> {message}")

        if response is not None:
            self.log_display.append(
                f"&lt;- Raw Response (Hex Stream): {response.hex().upper()}"
            )

        if decoded is not None:
            self.log_display.append(f"<b>[DECODED]</b> {decoded}")

        # ------------------------------------------
        # SESSION MANAGEMENT
        # ------------------------------------------
        if positive and sid == 0x10 and len(payload) >= 2:
            session_type = payload[1]

            if session_type == 0x02:
                self.tester_present.start()
                self.session_label.setText("Session: Programming")
                self.tester_present_label.setText("Tester Present: Active")
                self.log_display.append("✅ Programming Session Active (Keep-Alive Enabled)")

            elif session_type == 0x03:
                self.tester_present.start()
                self.session_label.setText("Session: Extended")
                self.tester_present_label.setText("Tester Present: Active")
                self.log_display.append("✅ Extended Diagnostic Session Active (Keep-Alive Enabled)")

            elif session_type == 0x01:
                self.tester_present.stop()
                self.session_label.setText("Session: Default")
                self.tester_present_label.setText("Tester Present: Inactive")
                self.log_display.append("↩️ Returning To Default Session (Keep-Alive Stopped)")

        self.log_display.append("-" * 40)

        # Re-enable the send button
        self.send_btn.setEnabled(True)

    def closeEvent(self, event):
        """Ensures the tester-present thread and CAN bus shut down cleanly."""
        try:
            if self.tester_present:
                self.tester_present.stop()
        except Exception:
            pass

        try:
            if self.bus:
                self.bus.shutdown()
        except Exception:
            pass

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DiagnosticsGUI()
    window.show()
    sys.exit(app.exec_())