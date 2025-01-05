import tkinter as tk
import threading
from enums.stateEnum import StateEnum as stateEnum
from services.cotral import Cotral_controller as cotralController
from services.meteo import Meteo_controller as meteoController
from services.clock import Clock_controller as clockController
import json
from services.display import Display_controller as displaycontroller
from time import sleep
class Hub:

    def __init__(self):
        self.current_state = None
        self.lock = threading.Lock()
        self.response = None

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
        palina = config['transport']['palina']
        palina_refresh = config['transport']['refresh']
        meteo_location = config['meteo']['location']
        meteo_refresh = config['meteo']['refresh']
        unit = config['meteo']['unit']
        display = config['display']['width'], config['display']['height']
        display_refresh = config['display']['refresh']
        clock_refresh = config['clock']['refresh']
        clock_format = config['clock']['format']

        self.hub_refresh = config['HUB']['refresh']
        # Initialize the controllers
        self.cotralController = cotralController(palina, palina_refresh)
        self.meteoController = meteoController(meteo_location, unit, meteo_refresh)
        self.clockController = clockController(clock_format, clock_refresh)
        self.displaycontroller = displaycontroller(display[0], display[1])
        
        self.startup_command()

        # Start display thread
        self.display_stop_flag = False
        self.display_thread = threading.Thread(target=self.async_main_loop)
        self.display_thread.start()


    def setStopFlag(self, status):
        self.display_stop_flag = status

    def StopAllThreads(self):
        self.meteoController.setStopFlag(True)
        self.cotralController.setStopFlag(True)
        self.clockController.setStopFlag(True)
        self.setStopFlag(True)
        
        if self.current_thread and self.current_thread.is_alive():
            self.current_thread.join()
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join()
        if self.meteoController.thread and self.meteoController.thread.is_alive():
            self.meteoController.thread.join()
        if self.cotralController.thread and self.cotralController.thread.is_alive():
            self.cotralController.thread.join()
        if self.clockController.thread and self.clockController.thread.is_alive():
            self.clockController.thread.join()
        


    def start_thread(self):
        thread = threading.Thread(target=self.startingup)
        thread.start()
        return thread

    def startingup(self):
        self.response="Starting up.."

    def startup_command(self):
        with self.lock:
            if self.current_state == stateEnum.STARTUP:
                print("service already started")
            else:
                self.current_state = stateEnum.STARTUP
                self.start_new_thread(self.current_state)

    # Commands for buttons
    def command1(self):
        with self.lock:
            self.current_state = list(stateEnum)[0]
            self.start_new_thread(self.current_state)

    def command2(self):
        with self.lock:
            self.current_state = list(stateEnum)[1]
            self.start_new_thread(self.current_state)

    def command3(self):
        with self.lock:
            self.current_state = list(stateEnum)[2]
            self.start_new_thread(self.current_state)

    def command4(self):
        with self.lock:
            self.current_state = list(stateEnum)[3]
            self.start_new_thread(self.current_state)

    def command5(self):
        with self.lock:
            self.current_state = list(stateEnum)[4]
            self.start_new_thread(self.current_state)        

    def start_new_thread(self, state):
        self.meteoController.setStopFlag(True)
        self.cotralController.setStopFlag(True)
        self.clockController.setStopFlag(True)
        match state:
            case stateEnum.STARTUP:
                self.current_thread = self.start_thread()
            case stateEnum.METEO:
                self.meteoController.start_thread()
            case stateEnum.COTRAL:
                self.cotralController.start_thread()
            case stateEnum.CLOCK:
                self.clockController.start_thread()
            case _:
                print("Invalid state.")

    def async_main_loop(self):
        data = None
        while not self.display_stop_flag:  
            with self.lock:
                match self.current_state:
                    case stateEnum.STARTUP:
                        data = self.response
                    case stateEnum.METEO:
                        data = self.meteoController.response
                    case stateEnum.COTRAL:
                        data = self.cotralController.response
                    case stateEnum.CLOCK:
                        data = self.clockController.response
                    case _:
                        print("Invalid state.")
            sleep(self.hub_refresh)
            self.displaycontroller.write_on_display(self.current_state, data)

# Function to handle window close event
def on_closing():
    print("Closing the window...")
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
    commands = [hub.command1, hub.command2, hub.command3, hub.command4, hub.command5]
    for i in range(5):
        btn = tk.Button(button_frame, text=f"Button {i+1}", command=commands[i])
        btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    # Start the GUI loop
    root.mainloop()

    print("Exiting...")

