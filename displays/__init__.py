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
    # Loop through all files in the folder
    """
    Dynamically imports all modules from a folder and adds controller class references
    for all matching objects (e.g., classes).
    
    Args:
        folder_path (str): The folder containing the modules.
        base_class (type): If specified, only load classes that are subclasses of this class.
    
    Returns:
        dict: A dictionary of controller class references, keyed by class name.
    """
    controllers = {}
    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]  # Remove ".py" to get the module name
            module = importlib.import_module(f"displays.{module_name}")  # Dynamically import the module
            
            # Store only the actual controller class (exclude Controller_template)
            for attr_name in dir(module):

                attr = getattr(module, attr_name)
                if isinstance(attr, type) and (base_class is None or issubclass(attr, base_class)):
                    if attr != base_class:
                        controllers[module_name] = attr  # Store the class reference (not the inner dict)
                        break  # Stop after storing the first valid controller class
    return controllers