from time import sleep
from datetime import datetime
from templates import Controller_template

class Clock_controller(Controller_template):
    def __init__(self,args):
        self.response = None
        self.thread = None
        self.stop_thread = False
        self.format =args["format"]
        self.refresh =args["refresh"]
        
    def thread_function(self):
        while not self.stop_thread:
            self.response = datetime.now().strftime("%d/%m/%Y  %H:%M")
            sleep(self.refresh)    