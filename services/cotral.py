import requests
import threading
import xml.etree.ElementTree as ET
from time import sleep
from templates.Controller_template import Controller_template

class Cotral_controller(Controller_template):
    def __init__(self, args):
        # Initialize URLs and stop index
        self.cotral_stop = args["palina"]
        self.response = None
        self.thread = threading.Thread(target=self.thread_function)
        self.stop_thread = False
        self.cotral_url = "http://travel.mob.cotralspa.it:7777/beApp/PIV.do"
        self.refresh = args["refresh"]
    def thread_function(self):
        Interested_data = ["arrivoCorsa","tempoTransito","ritardo"]

        params={
            'cmd': 1,
            'userId': 1,
            'pCodice': self.cotral_stop
        }
        while not self.stop_thread:
            self.response=requests.get(self.cotral_url,params=params)
            xml_data = self.response.text
            data = []
            for child in ET.fromstring(xml_data):
                child_data = {child.tag: child.text for child in child}
                data.append(child_data)

            filtered_data = []
            seen_arrivals = set()
            for entry in data[1:]:
                filtered_entry = {k: v for k, v in entry.items() if k in Interested_data and v}
                if filtered_entry.get("arrivoCorsa") and filtered_entry["arrivoCorsa"] not in seen_arrivals:
                    seen_arrivals.add(filtered_entry["arrivoCorsa"])
                    # Convert tempoTransito from minutes since the start of the day to daily time
                    seconds_since_start = int(filtered_entry.get("tempoTransito"))
                    minutes_since_start = seconds_since_start // 60
                    seconds= seconds_since_start % 60
                    hours = minutes_since_start // 60
                    minutes = minutes_since_start % 60
                    daily_time = f"{hours:02}:{minutes:02}:{seconds:02}"
                    
                    filtered_data.append([
                        filtered_entry.get("arrivoCorsa"),
                        daily_time,
                        filtered_entry.get("ritardo")
                    ])

            data = filtered_data


            self.response = data
            sleep(self.refresh)