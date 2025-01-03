import tkinter as tk
from enums.stateEnum import StateEnum as stateEnum
from services.cotral import Cotral_controller as cotralController
from services.meteo import Meteo_controller as meteoController
import json

class Hub:

    current_state = stateEnum.IDLE

    # Commands for buttons
    def command1():
        print("Command 1 executed")

    def command2():
        print("Command 2 executed")

    def command3():
        print("Command 3 executed")

    def command4():
        print("Command 4 executed")

    def command5():
        print("Command 5 executed")

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
            location = "Monterotondo"
            unit = "C"

        self.cotralController = cotralController(palina)
        self.meteoController = meteoController(location, unit)

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
    commands = [Hub.command1, Hub.command2, Hub.command3, Hub.command4, Hub.command5]
    for i in range(5):
        btn = tk.Button(button_frame, text=f"Button {i+1}", command=commands[i])
        btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    # Start the GUI loop
    root.mainloop()

    print("Exiting...")
    
    