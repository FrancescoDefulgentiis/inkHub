import requests
import threading
import pandas as pd
import xml.etree.ElementTree as ET
from time import sleep

class Cotral_controller:
    def __init__(self, stop_index):
        # Initialize URLs and stop index
        self.cotral_stop = stop_index
        self.response = None
        self.thread = None
        self.stop_thread = False
        self.cotral_url = "http://travel.mob.cotralspa.it:7777/beApp/PIV.do"


    def setStopFlag(self, status):
        self.stop_thread = status


    def start_thread(self):
        self.stop_thread = False
        self.thread = threading.Thread(target=self.thread_function)
        self.thread.start()
    def thread_function(self):
        params={
            'cmd': 1,
            'userId': 1,
            'pCodice': self.cotral_stop
        }
        print("thread started")
        while not self.stop_thread:
            self.response=requests.get(self.cotral_url,params=params)
            xml_data = self.response.text
            data = []
            for child in ET.fromstring(xml_data):
                child_data = {child.tag: child.text for child in child}
                data.append(child_data)
            self.response = pd.DataFrame(data)
            sleep(10)