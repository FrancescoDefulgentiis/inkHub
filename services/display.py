class Display_controller:
    def __init__(self, width, height):
        self.width = width
        self.height = height
    def write_on_display(self,state,message):
        print(f"State: {state} - Message: {message}")