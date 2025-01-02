import requests
import threading
import pandas as pd
import xml.etree.ElementTree as ET
import time
#COTRAL_STOP="f13837"
class Cotral_controller:
    def __init__(self,stop_index):
        self.stop_url="PIV.do?cmd=1&userId=1&pCodice="
        self.cotral_url="http://travel.mob.cotralspa.it:7777/beApp/"
        self.cotral_stop=stop_index
        self.thread=threading.Thread(target=self.Get_data)
        self.dataframe=pd.DataFrame()
        self.thread.start()
        self.stop_thread=False
    def Get_data(self):
        print("thread started")
        while self.stop_thread==False:
            response = requests.get(f"{self.cotral_url}{self.stop_url}{self.cotral_stop}")
            xml_data=response.text
            data=[]
            for child in ET.fromstring(xml_data):
                child_data={child.tag:child.text for child in child}
                data.append(child_data)
            self.dataframe=pd.DataFrame(data)
            time.sleep(10)