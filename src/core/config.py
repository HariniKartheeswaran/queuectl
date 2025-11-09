"""
Configuration Management
"""

import os
import json
from pathlib import Path

class Config:
    """Application configuration"""
    
    def __init__(self):
        # Database settings
        self.db_path = os.getenv('QUEUECTL_DB_PATH', 'data/jobs.json')
        
        # Worker settings
        self.poll_interval = float(os.getenv('QUEUECTL_POLL_INTERVAL', '1.0'))
        self.backoff_base = int(os.getenv('QUEUECTL_BACKOFF_BASE', '2'))
        
        # Job defaults
        self.default_max_retries = int(os.getenv('QUEUECTL_MAX_RETRIES', '3'))
        self.default_timeout = int(os.getenv('QUEUECTL_TIMEOUT', '300'))
        
        # Logging
        self.log_level = os.getenv('QUEUECTL_LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('QUEUECTL_LOG_FILE', 'data/queuectl.log')
        
        # Load saved config if exists
        self._load_saved_config()
        
        # Create data directory
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
    
    def _load_saved_config(self):
        """Load saved configuration from file"""
        config_file = Path('data/config.json')
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    saved_config = json.load(f)
                    
                # Override with saved values
                if 'default_max_retries' in saved_config:
                    self.default_max_retries = saved_config['default_max_retries']
                if 'backoff_base' in saved_config:
                    self.backoff_base = saved_config['backoff_base']
                if 'poll_interval' in saved_config:
                    self.poll_interval = saved_config['poll_interval']
                if 'default_timeout' in saved_config:
                    self.default_timeout = saved_config['default_timeout']
            except Exception:
                pass  # Ignore errors loading config
    
    def __repr__(self):
        return (
            f"Config(db_path={self.db_path}, "
            f"backoff_base={self.backoff_base}, "
            f"poll_interval={self.poll_interval})"
        )
