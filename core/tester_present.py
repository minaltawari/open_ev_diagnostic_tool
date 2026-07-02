import threading
import time

class TesterPresentManager:
    def __init__(self, engine):
        self.engine = engine
        self.running = False
        self.thread = None

    def _worker(self):
        while self.running:
            try:
                # 0x3E (TesterPresent), 0x80 (suppressPositiveResponseMsgIndication)
                self.engine.send(bytes([0x3E, 0x80]))
            except Exception as e:
                # It's better to print or log the error rather than silently passing, 
                # so you know if your connection drops.
                print(f"[TesterPresent] Failed to send: {e}")
            
            # FIXED: This must be INSIDE the while loop!
            # 2 seconds is standard for keeping a UDS session alive.
            time.sleep(2)

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._worker,
            daemon=True  # Crucial: This ensures the thread dies when your main program closes
        )
        self.thread.start()

    def stop(self):
        self.running = False
        # Optional but good practice: Wait for the thread to cleanly exit
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.5)