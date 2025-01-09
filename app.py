import tkinter as tk
import threading
from services import __path__ as services_path  # Get the services folder path
from services import load_controllers
from displays import __path__ as displays_path
from displays import load_displays
from templates import Display_template,Controller_template
import displays
import subprocess
import os
import json
from time import sleep

class Hub:

    def __init__(self):
        self.current_state = None
        self.lock = threading.Lock()
        self.response = "starting app .."

        try:
            with open('config/config.json', 'r') as file:
                config = json.load(file)
        except FileNotFoundError:
            print("Config file not found.")
            config = {}
        except json.JSONDecodeError:
            print("Error decoding JSON from the config file.")
            config = {}
        
        if not config:
            config ={
                "HUB":{
                "refresh": 0.1
                },
                "transport": {
                    "palina": "f13837",
                    "refresh": 30000
                },
                "Weather": {
                    "location": "3172768",
                    "unit": "metric",
                    "refresh": 300000
                },
                "display": {
                    "width": 128,
                    "height": 64,
                    "refresh": 1000
                },
                "clock":{
                    "format": "Y/M/D  HH:mm",
                    "refresh": 60
                }
                }
            print("Config file is empty, using default values.")
            with open('config/config.json', 'w') as file:
                json.dump(config, file, indent=4)

        self.hub_refresh = config["HUB"]["refresh"]

        controller_path = os.path.abspath(services_path[0])
        self.controllers=load_controllers(controller_path,base_class=Controller_template)
        self.Enum_list=list(self.controllers.keys())

        for element in self.Enum_list:
            if config.get(element.lower(),):
                controller_class = self.controllers[element.lower()] 
                self.controllers[element] = controller_class(config[element.lower()])
            if config.get(element.upper()):
                controller_class = self.controllers[element] 
                self.controllers[element] = controller_class(config[element.upper()]) 
                display_path= os.path.abspath(displays_path[0])
                
        self.displays=load_displays(display_path,base_class=Display_template)

        for display in self.displays.keys():
            self.displays[display]=self.displays[display]()

        self.displays[None]=Display_template()

        self.display_stop_flag=False
        self.display_thread = threading.Thread(target=self.async_main_loop)
        self.display_thread.start()

    def main_loop(self,terminal_path):
  # Redirect input and output to another terminal
        with open(terminal_path, 'w+') as terminal:
            original_stdout = os.dup(1)
            original_stdin = os.dup(0)
            os.dup2(terminal.fileno(), 1)
            os.dup2(terminal.fileno(), 0)
            try:
                while not self.display_stop_flag:
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print("SELEZIONARE MODALITA':\n 0 CLOCK \n 1 COTRAL \n 2 METEO \n 4 Esci")
                    state = int(input())
                    if state == 4:
                        self.StopAllThreads()
                    else:
                        self._command(state)
            finally:
                os.dup2(original_stdout, 1)
                os.dup2(original_stdin, 0)
                os.close(original_stdout)
                os.close(original_stdin)

    def setStopFlag(self, status):
        self.display_stop_flag = status

    def StopAllThreads(self):
        self.setStopFlag(True)
        for item in self.controllers.values():
            item.setStopFlag(True)
            if item.thread and  item.thread.is_alive():
                item.thread.join()

    def create_command(self, index):
        return lambda: self._command(index)
    
    def _command(self, index):
        with self.lock:
            self.current_state = self.Enum_list[index]
            self.start_new_thread(self.current_state)
   
    def start_new_thread(self, state):
        for item in self.controllers.values():

            item.setStopFlag(True)
        for item in self.displays.values():
            if item!=self.displays[self.current_state]:
                item.reset_data()
        self.controllers[state].start_thread()

    def async_main_loop(self):
        while not self.display_stop_flag:  
            with self.lock:
                self.displays.get(self.current_state,Display_template())._write_on_display(self.controllers.get(self.current_state,self).response)
                sleep(self.hub_refresh)

if __name__ == "__main__":
   
    hub = Hub()
    terminal_path = '/dev/pts/1'  # Replace with the correct terminal path
    hub.main_loop(terminal_path)

