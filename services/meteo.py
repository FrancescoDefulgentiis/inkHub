import requests
import threading
import os
from time import sleep
from dotenv import load_dotenv
class Meteo_controller:
    def __init__(self, locationId, unit,refresh):
        load_dotenv()
        self.locationId = locationId
        self.unit = unit
        self.stop_flag= False
        self.response = None
        self.thread = None
        self.appid = os.getenv('OPENWEATHER_API_KEY')
        self.base_url = 'http://api.openweathermap.org/data/2.5//forecast'
        self.refresh = refresh
    def setStopFlag(self, status):
        self.stop_flag = status
        
    def thread_function(self):

        params = {
            'id': self.locationId,
            'units': self.unit,
            'appid': self.appid,
            'lang': 'en',
            'mode': 'json'
        }
        
        while not self.stop_flag:
            url = requests.Request('GET', self.base_url, params=params).prepare().url
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                #analisi e scrematura dati
                self.response = data
            else:
                print("Error while fetching data from the API")
                print("Status code: ", response.status_code)

            sleep(self.refresh)
        
    def start_thread(self,):
        self.stop_flag = False
        self.thread = threading.Thread(target=self.thread_function)
        self.thread.start()
