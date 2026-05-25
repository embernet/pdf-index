import json
import os

class ConfigManager:
    DEFAULT_CONFIG = {
        "pdf_filename": None,
        "strategy": "logical",
        "offset": 0,
        "view_mode": "active",
        "capitalize": False,
        "view_source": False,
        "fit_page": True,
        "name_indexing": True,
        "index_capitalised": True,
        "bold_indexing": True,
        "index_single_quotes": True,
        "single_quote_max_chars": 100,
        "italic_max_chars": 100,
        "bold_max_chars": 100,
        "index_from_offset": True,
        "surname_first": False,
        "index_italic": True,
        "separate_style_files": True,
        "generate_web_bundle": False,
        "index_front_matter_roman": True,
        "style_view": "aggregate",
        "llm_enrichment_enabled": False,
        "llm_host": "http://localhost:11434",
        "llm_hosts": ["http://localhost:11434"],
        "llm_model": "qwen2.5:7b",
        "llm_subindex_threshold": 8,
        "llm_subindex_enabled": True,
        "llm_alias_enabled": True,
        "llm_category_enabled": True,
        "llm_seealso_enabled": True,
    }

    @staticmethod
    def load_config(project_path):
        config_path = os.path.join(project_path, "config.json")
        if not os.path.exists(config_path):
            return ConfigManager.DEFAULT_CONFIG.copy()
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return ConfigManager.DEFAULT_CONFIG.copy()
        config = ConfigManager.DEFAULT_CONFIG.copy()
        config.update(data)
        # Migrate legacy singular llm_host -> llm_hosts list when the new
        # key was absent from the on-disk file. Keep llm_host populated
        # too for one-cycle back-compat in case anything still reads it.
        if "llm_hosts" not in data and isinstance(data.get("llm_host"), str):
            config["llm_hosts"] = [data["llm_host"]]
        return config

    @staticmethod
    def save_config(project_path, config_data):
        config_path = os.path.join(project_path, "config.json")
        try:
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
