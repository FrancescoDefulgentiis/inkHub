class Display_template():

    def __init__(self):
        self.data=None

    def _write_on_display(self,data):
        if data and self.data!=data:
            self.data=data
            self.write_on_display()
            
    def write_on_display(self):
        print(self.data)

