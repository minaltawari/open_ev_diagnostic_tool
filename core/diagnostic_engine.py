import time

class DiagnosticEngine:

    def __init__(
        self,
        stack
    ):

        self.stack = stack

    def send(
        self,
        payload
    ):

        self.stack.send(payload)

        while self.stack.transmitting():

            self.stack.process()

            time.sleep(0.005)

    def receive(
        self,
        timeout
    ):

        start = time.time()

        while (
            time.time() - start
        ) < timeout:

            self.stack.process()

            if self.stack.available():

                return self.stack.recv()

            time.sleep(0.01)

        return None