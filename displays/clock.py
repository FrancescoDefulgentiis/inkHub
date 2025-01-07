from templates.Display_template import Display_template

class Clock_display(Display_template):
    def write_on_display(self):
        print(self.data)