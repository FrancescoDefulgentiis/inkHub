import requests
import threading
import pandas as pd
import xml.etree.ElementTree as ET
from time import sleep

class Cotral_controller:
    def __init__(self, stop_index):
        # Initialize URLs and stop index
        self.stop_url = "PIV.do?cmd=1&userId=1&pCodice="
        self.cotral_url = "http://travel.mob.cotralspa.it:7777/beApp/"
        self.cotral_stop = stop_index
        self.stop_thread = False
        
        # Create a thread to fetch data
        self.thread = threading.Thread(target=self.Get_data)
        
        # Initialize an empty DataFrame to store data
        self.dataframe = pd.DataFrame()
        
        # Start the thread
        self.thread.start()
        
        # Flag to stop the thread


    def setStopFlag(self, status):
        self.stop_thread = status

    def Get_data(self):
        print("thread started")
        
        # Loop to fetch data until stop_thread is set to True
        while not self.stop_thread:
            # Send a GET request to the Cotral API
            response = requests.get(f"{self.cotral_url}{self.stop_url}{self.cotral_stop}")
            
            # Parse the XML response
            xml_data = response.text
            data = []
            for child in ET.fromstring(xml_data):
                # Extract data from each XML element
                child_data = {child.tag: child.text for child in child}
                data.append(child_data)
            
            # Update the DataFrame with the new data
            self.dataframe = pd.DataFrame(data)
            
            # Sleep for 10 seconds before the next request
            sleep(10)