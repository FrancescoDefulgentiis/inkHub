import tkinter as tk
import threading
from enums.stateEnum import StateEnum as stateEnum
from services.cotral import Cotral_controller as cotralController
from services.meteo import Meteo_controller as meteoController
import json
from time import sleep

class Hub:

    stop_event = threading.Event() 
    current_thread = None  
    current_state = None

    def __init__(self):

        # Load config file
        try:
            with open('../config/config.json', 'r') as file:
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
        else:
            print("Config file is empty, using default values.")
            palina = "f13837"
            location = "3172768"
            unit = "metric"

        self.cotralController = cotralController(palina)
        self.meteoController = meteoController(location, unit)
        self.startup_command()

    def start_thread(self):
        thread = threading.Thread(target=self.startingup, args=(self.stop_event,))
        thread.start()
        return thread

    def startingup(self):
        print("Starting up...")

    def startup_command(self):
        if self.current_state == stateEnum.STARTUP:
            print("service already started")
        else:
            current_state = stateEnum.STARTUP
            self.start_new_thread(current_state)

    # Commands for buttons
    def command1(self):
        if self.current_state == stateEnum.METEO:
            print("service already started")
        else:
            current_state = stateEnum.METEO
            self.start_new_thread(current_state)

    def command2(self):
        if self.current_state == stateEnum.COTRAL:
            print("service already started")
        else:
            current_state = stateEnum.COTRAL
            self.start_new_thread(current_state)

    def command3(self):
        pass

    def command4(self):
        pass

    def command5(self):
        print("command 5")
        pass            

    def start_new_thread(self, state):
        if self.current_thread is not None and self.current_thread.is_alive():
            self.stop_event.set()
            self.current_thread.join()
        self.stop_event.clear()

        match state:
            case stateEnum.STARTUP:
                self.current_thread = self.start_thread()
            case stateEnum.METEO:
                self.current_thread = self.meteoController.start_thread(self.stop_event)
                
            case _:
                print("Invalid state.")

# Function to handle window close event
def on_closing():
    print("Closing the window...")
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

    # Information display section
    info_label = tk.Label(root, text="Welcome to the Home Hub!", bg="white", anchor="w", relief="solid")
    info_label.pack(fill=tk.BOTH, padx=5, pady=5)

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
    
    