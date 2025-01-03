import requests
import threading
import os
from time import sleep

class Meteo_controller:
    def __init__(self, locationId, unit):
        self.locationId = locationId
        self.unit = unit
        self.appid = os.getenv('OPENWEATHER_API_KEY')
        self.base_url = 'http://api.openweathermap.org/data/2.5//forecast'
        
    def thread_function(self):

        params = {
            'id': self.locationId,
            'units': self.unit,
            'appid': self.appid,
            'lang': 'en',
            'mode': 'json'
        }

        while True:

            response = requests.get(self.base_url, params=params)
        
            if response.status_code == 200:
                print(response.json())
            else:
                print("Error while fetching data from the API")
            
            sleep(900)
        
    def start_thread(self, stop_event):
        thread = threading.Thread(target=self.thread_function, args=(stop_event,))
        thread.start()
        return thread
