import os
import yaml

class Config:
    """Dynamic YAML-based config"""

    def __init__(self, path="config.yaml"):
        self.path = os.path.join(os.path.dirname(__file__), path)
        self.reload()

    def reload(self):
        """Reload YAML from disk"""
        with open(self.path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

    def get(self, *keys, default=None):
        """Get nested keys from YAML, e.g. get('filter_check', 'allowed_roles')"""
        data = self._data
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key, default)
        return data

# global instance
config = Config()