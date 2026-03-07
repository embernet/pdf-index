import json
import os

class AppConfigManager:
    CONFIG_FILE = "app_config.json"
    
    DEFAULT_CONFIG = {
        "recent_projects": [],
        "last_opened_project": None
    }

    @staticmethod
    def get_config_path():
        # Save in the same directory as main.py for portability or user home?
        # User requested "the app remembers". Relative to CWD is easiest for portable app.
        return os.path.abspath(AppConfigManager.CONFIG_FILE)

    @staticmethod
    def load_config():
        path = AppConfigManager.get_config_path()
        if not os.path.exists(path):
            return AppConfigManager.DEFAULT_CONFIG.copy()
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                config = AppConfigManager.DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception as e:
            print(f"Error loading app config: {e}")
            return AppConfigManager.DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(config_data):
        path = AppConfigManager.get_config_path()
        try:
            with open(path, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving app config: {e}")

    @staticmethod
    def add_recent_project(project_path):
        config = AppConfigManager.load_config()
        recent = config.get("recent_projects", [])
        
        # Remove if exists to move to top
        if project_path in recent:
            recent.remove(project_path)
            
        recent.insert(0, project_path)
        
        # Limit to 20
        recent = recent[:20]
        
        config["recent_projects"] = recent
        config["last_opened_project"] = project_path
        
        AppConfigManager.save_config(config)

    @staticmethod
    def get_last_project():
        config = AppConfigManager.load_config()
        return config.get("last_opened_project")
