import time
from datetime import datetime
import threading

class Clock_controller:
    def __init__(self,formato,refresh):
        self.response = None
        self.thread = None
        self.stop_thread = False
        self.format = formato
        self.refresh = refresh
    
    def setStopFlag(self, status):
        self.stop_thread = status
    
    def start_thread(self):
        self.stop_thread = False
        self.thread = threading.Thread(target=self.thread_function)
        self.thread.start()

    def thread_function(self):
        while not self.stop_thread:

            self.response = datetime.now().strftime("%d/%m/%Y  %H:%M")
            time.sleep(self.refresh)