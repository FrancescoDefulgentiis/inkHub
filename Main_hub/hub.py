import tkinter as tk
import threading
from enums.stateEnum import StateEnum as stateEnum
from services.cotral import Cotral_controller as cotralController
from services.meteo import Meteo_controller as meteoController
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
        if config:
            palina = config['transport']['palina']
            location = config['meteo']['location']
            unit = config['meteo']['unit']
            display = config['display']['width'], config['display']['height']
        else:
            print("Config file is empty, using default values.")
            palina = "f13837"
            location = "3172768"
            unit = "metric"
            display = 128, 64
            
            config = {
                "transport": {
                    "palina": "f13837"
                },
                "meteo": {
                    "location":"3172768",
                    "unit":"metric"
                },
                "display": {
                    "width": 128,
                    "height": 64
                }
            }
            with open('config/config.json', 'w') as file:
                json.dump(config, file, indent=4)

        # Initialize the controllers
        self.cotralController = cotralController(palina)
        self.meteoController = meteoController(location, unit)
        self.displaycontroller = displaycontroller(display[0], display[1])
        
        self.startup_command()

        # Start display thread
        self.display_stop_flag = False
        self.display_thread = threading.Thread(target=self.async_main_loop)
        self.display_thread.start()

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
            if self.current_state == stateEnum.METEO:
                print("service already started")
            else:
                self.current_state = stateEnum.METEO
                self.start_new_thread(self.current_state)

    def command2(self):
        with self.lock:
            if self.current_state == stateEnum.COTRAL:
                print("service already started")
            else:
                self.current_state = stateEnum.COTRAL
                self.start_new_thread(self.current_state)

    def command3(self):
        pass

    def command4(self):
        pass

    def command5(self):
        print("command 5")
        pass            

    def start_new_thread(self, state):
        self.meteoController.setStopFlag(True)
        self.cotralController.setStopFlag(True)
    
        match state:
            case stateEnum.STARTUP:
                self.current_thread = self.start_thread()

            case stateEnum.METEO:
                self.meteoController.start_thread()
                
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
                    case _:
                        print("Invalid state.")
            sleep(0.1)
            self.displaycontroller.write_on_display(self.current_state, data)

# Function to handle window close event
def on_closing():
    print("Closing the window...")
    # Set the stop flag to True to stop the display thread
    hub.display_stop_flag = True
    hub.meteoController.stop_flag = True
    hub.cotralController.stop_flag = True
    # Wait for the display thread to finish
    hub.display_thread.join()
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
