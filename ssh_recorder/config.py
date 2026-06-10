import os
from typing import Dict, Any, Optional


class ServerConfig:
    def __init__(
        self,
        name: str,
        host: str,
        user: str,
        port: int = 22,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        self.name = name
        self.host = host
        self.user = user
        self.port = port
        self.password = password
        self.key_file = os.path.expanduser(key_file) if key_file else None
        self.passphrase = passphrase

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, Any]) -> "ServerConfig":
        return cls(
            name=name,
            host=d["host"],
            user=d["user"],
            port=d.get("port", 22),
            password=d.get("password"),
            key_file=d.get("key_file"),
            passphrase=d.get("passphrase"),
        )


class ConfigLoader:
    @staticmethod
    def load_servers(config_file: str) -> Dict[str, ServerConfig]:
        import yaml

        config_file = os.path.expanduser(config_file)
        if not os.path.exists(config_file):
            return {}

        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        servers = {}
        for name, cfg in (data.get("servers") or {}).items():
            servers[name] = ServerConfig.from_dict(name, cfg)
        return servers

    @staticmethod
    def get_server(config_file: str, name: str) -> Optional[ServerConfig]:
        servers = ConfigLoader.load_servers(config_file)
        return servers.get(name)
