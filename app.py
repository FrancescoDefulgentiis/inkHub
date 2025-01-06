import tkinter as tk
import threading
from services import __path__ as services_path  # Get the services folder path
from services import load_controllers
import Controller_template
import os
import json
from displays.display import Display_controller as displaycontroller
from time import sleep
class Hub:

    def __init__(self):
        self.current_state = None
        self.lock = threading.Lock()
        self.response = "starting app .."
        # Load config file
        try:
            with open('config/config.json', 'r') as file:
                config = json.load(file)
        except FileNotFoundError:
            print("Config file not found.")
            config = {}
        except json.JSONDecodeError:
            print("Error decoding JSON from the config file.")
            config = {}
        
        # Load the data from the config file
        if not config:
            config ={
                "HUB":{
                "refresh": 0.1
                },
                "transport": {
                    "palina": "f13837",
                    "refresh": 30000
                },
                "meteo": {
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

        # Load the refresh rate for the hub
        self.hub_refresh = config["HUB"]["refresh"]

        #Load data from the config file and initialize the controllers dinamically
        folder_path = os.path.abspath(services_path[0])
        self.controllers=load_controllers(folder_path,base_class=Controller_template.Controller_template)
        self.Enum_list=list(self.controllers.keys())
        for element in self.Enum_list:
            if config.get(element.lower(),):
                controller_class = self.controllers[element.lower()] 
                self.controllers[element] = controller_class(config[element.lower()])
            if config.get(element.upper()):
                controller_class = self.controllers[element] 
                self.controllers[element] = controller_class(config[element.upper()]) 

        

        # Start display thread
        display = [config.get("DISPLAY", {}).get("width", 128), config.get("DISPLAY", {}).get("height", 64)]
        self.displaycontroller = displaycontroller(display[0], display[1])
        self.display_stop_flag = False
        self.display_thread = threading.Thread(target=self.async_main_loop)
        self.display_thread.start()


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
        self.controllers[state].start_thread()
        
    def async_main_loop(self):
        while not self.display_stop_flag:  
            with self.lock:
                    data = self.controllers.get(self.current_state)
                    if data:
                        data=data.response
                    else:
                        data = self.response
                    self.displaycontroller.write_on_display(self.current_state, data)
                    sleep(self.hub_refresh)

# Function to handle window close event
def on_closing():
    # Set the stop flag to True to stop the display thread
    hub.StopAllThreads()
    # Wait for the display thread to finish
    # Close the window
    root.quit()  
    root.destroy()  

if __name__ == "__main__":
    hub = Hub()

    # Create the main window
    root = tk.Tk()
    root.title("Home Hub")
    root.geometry("400x300")  # Set the size of the window

    # Bind the window close event to the on_closing function
    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Button section
    button_frame = tk.Frame(root)
    button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

    # Add five buttons
    for i in range(len(hub.Enum_list)):
        btn = tk.Button(button_frame, text=f"{hub.Enum_list[i]}", command=hub.create_command(i))
        btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    # Start the GUI loop
    root.mainloop()

    print("Exiting...")

