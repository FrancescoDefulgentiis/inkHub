import threading

class Controller_template:

    def __init__(self,args):
        self.response = None
        self.thread = None
        self.stop_thread = False
        self.refresh =args["refresh"]

    def thread_function(self):
        self.response = "No thread function defined"
        while not self.stop_thread:
            pass

    def start_thread(self,):
        if  not self.thread:    
            self.stop_thread = False
            self.thread = threading.Thread(target=self.thread_function)     
            self.thread.start()
        else:
            if self.thread.is_alive():
                self.stop_thread = False
            else:
                self.stop_thread = False
                self.thread = threading.Thread(target=self.thread_function)     
                self.thread.start()
    def setStopFlag(self, status):
        self.stop_thread = status