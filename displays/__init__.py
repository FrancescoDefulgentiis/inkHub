import importlib
import os
__all__ = [
    "load_displays"
]

def load_displays(folder_path, base_class=None):
    """
    Dynamically loads all display classes that inherit from the given base_class
    from the specified folder and returns them in a dictionary with their module name as the key.
    """
    displays = {}
    
    # Ensure the folder path is relative to the script location
    folder_path = os.path.abspath(folder_path)  # Convert to absolute path
    folder_name = os.path.basename(folder_path)  # Get the last part of the path (e.g., 'displays')

    # Loop through all files in the folder
    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":  # Ignore init files
            module_name = file[:-3]  # Remove ".py" to get the module name
            module_full_name = f"{folder_name}.{module_name}"  # Construct module name relative to the folder

            try:
                # Dynamically import the module
                module = importlib.import_module(module_full_name)

                # Store only the classes that inherit from base_class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and (base_class is None or issubclass(attr, base_class)):
                        if attr_name != 'Display_template':  # Avoid storing base class
                            displays[module_name] = attr  # Store the class reference
                            break  # Stop after storing the first valid class
            except ModuleNotFoundError:
                print(f"Module {module_full_name} not found.")
    
    return displays