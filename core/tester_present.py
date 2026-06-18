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

              self.engine.send(
                bytes([0x3E, 0x80])
            )

            except Exception:
              pass

        time.sleep(2)

    def start(self):

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._worker,
            daemon=True
        )

        self.thread.start()

    def stop(self):

        self.running = False
