#import os_fork_extend
#import RPi.GPIO as GPIO
import cotral
import time
import pandas as pd
import threading
class Hub:
    def __init__(self):
        self.cotral_controller=cotral.Cotral_controller("f13837")
 #       self.GPIO_controller=GPIO_controller()
    def refresh_data(self):
            print(self.cotral_controller.dataframe)
hub=Hub()

print(hub.cotral_controller.dataframe)
time.sleep(10)
hub.refresh_data()
print(hub.cotral_controller.dataframe)
hub.cotral_controller.stop_thread=True

