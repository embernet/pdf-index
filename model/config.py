import json
import os

class ConfigManager:
    DEFAULT_CONFIG = {
        "pdf_filename": None,
        "strategy": "logical",
        "offset": 1,
        "view_mode": "markdown",
        "capitalize": False,
        "view_source": False,
        "fit_width": True,
        "name_indexing": False
    }

    @staticmethod
    def load_config(project_path):
        config_path = os.path.join(project_path, "config.json")
        if not os.path.exists(config_path):
            return ConfigManager.DEFAULT_CONFIG.copy()
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                # Merge with defaults to ensure all keys exist
                config = ConfigManager.DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception as e:
            print(f"Error loading config: {e}")
            return ConfigManager.DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(project_path, config_data):
        config_path = os.path.join(project_path, "config.json")
        try:
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
