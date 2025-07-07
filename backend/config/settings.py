import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class RedisConfig:
    """Redis configuration settings"""
    url: str
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30
    
    @classmethod
    def from_env(cls) -> 'RedisConfig':
        redis_password = os.getenv("REDIS_PASSWORD", "defaultpassword123")
        return cls(
            url=os.getenv("REDIS_URL", f"redis://:{redis_password}@localhost:6379"),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")),
            socket_connect_timeout=float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0")),
            retry_on_timeout=os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true",
            health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
        )

@dataclass
class CacheConfig:
    """Cache configuration settings"""
    translation_ttl: int = 86400  # 24 hours
    language_detection_ttl: int = 3600  # 1 hour
    user_session_ttl: int = 3600  # 1 hour
    message_history_max: int = 50
    stats_update_interval: int = 60  # 1 minute
    
    @classmethod
    def from_env(cls) -> 'CacheConfig':
        return cls(
            translation_ttl=int(os.getenv("CACHE_TRANSLATION_TTL", "86400")),
            language_detection_ttl=int(os.getenv("CACHE_LANGUAGE_DETECTION_TTL", "3600")),
            user_session_ttl=int(os.getenv("CACHE_USER_SESSION_TTL", "3600")),
            message_history_max=int(os.getenv("CACHE_MESSAGE_HISTORY_MAX", "50")),
            stats_update_interval=int(os.getenv("CACHE_STATS_UPDATE_INTERVAL", "60"))
        )

@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    enabled: bool = True
    max_requests: int = 10
    window_seconds: int = 60
    translation_max_requests: int = 30
    translation_window_seconds: int = 60
    
    @classmethod
    def from_env(cls) -> 'RateLimitConfig':
        return cls(
            enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
            max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "10")),
            window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
            translation_max_requests=int(os.getenv("RATE_LIMIT_TRANSLATION_MAX_REQUESTS", "30")),
            translation_window_seconds=int(os.getenv("RATE_LIMIT_TRANSLATION_WINDOW_SECONDS", "60"))
        )

@dataclass
class AnthropicConfig:
    """Anthropic/Claude API configuration"""
    api_key: str
    model: str = "claude-3-5-haiku-20241022"
    max_tokens: int = 1000
    temperature: float = 0.1
    timeout: float = 1.5
    
    @classmethod
    def from_env(cls) -> 'AnthropicConfig':
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        return cls(
            api_key=api_key,
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1000")),
            temperature=float(os.getenv("ANTHROPIC_TEMPERATURE", "0.1")),
            timeout=float(os.getenv("ANTHROPIC_TIMEOUT", "1.5"))
        )

@dataclass
class ServerConfig:
    """Server configuration settings"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list = None
    instance_id: str = "default"
    
    @classmethod
    def from_env(cls) -> 'ServerConfig':
        cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
        return cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8000")),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            cors_origins=cors_origins,
            instance_id=os.getenv("INSTANCE_ID", "default")
        )

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    
    @classmethod
    def from_env(cls) -> 'LoggingConfig':
        return cls(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            file_path=os.getenv("LOG_FILE_PATH"),
            max_file_size=int(os.getenv("LOG_MAX_FILE_SIZE", str(10 * 1024 * 1024))),
            backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5"))
        )

@dataclass
class MonitoringConfig:
    """Monitoring and metrics configuration"""
    enabled: bool = True
    stats_collection_interval: int = 60
    health_check_interval: int = 30
    cleanup_interval: int = 3600  # 1 hour
    retention_days: int = 7
    
    @classmethod
    def from_env(cls) -> 'MonitoringConfig':
        return cls(
            enabled=os.getenv("MONITORING_ENABLED", "true").lower() == "true",
            stats_collection_interval=int(os.getenv("MONITORING_STATS_INTERVAL", "60")),
            health_check_interval=int(os.getenv("MONITORING_HEALTH_CHECK_INTERVAL", "30")),
            cleanup_interval=int(os.getenv("MONITORING_CLEANUP_INTERVAL", "3600")),
            retention_days=int(os.getenv("MONITORING_RETENTION_DAYS", "7"))
        )

class Settings:
    """Application settings container"""
    
    def __init__(self):
        self.redis = RedisConfig.from_env()
        self.cache = CacheConfig.from_env()
        self.rate_limit = RateLimitConfig.from_env()
        self.anthropic = AnthropicConfig.from_env()
        self.server = ServerConfig.from_env()
        self.logging = LoggingConfig.from_env()
        self.monitoring = MonitoringConfig.from_env()
    
    def validate(self) -> list:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Validate required API key
        if not self.anthropic.api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        
        # Validate Redis URL format
        if not self.redis.url.startswith(("redis://", "rediss://")):
            errors.append("REDIS_URL must start with redis:// or rediss://")
        
        # Validate rate limiting values
        if self.rate_limit.max_requests <= 0:
            errors.append("RATE_LIMIT_MAX_REQUESTS must be greater than 0")
        
        if self.rate_limit.window_seconds <= 0:
            errors.append("RATE_LIMIT_WINDOW_SECONDS must be greater than 0")
        
        # Validate cache TTL values
        if self.cache.translation_ttl <= 0:
            errors.append("CACHE_TRANSLATION_TTL must be greater than 0")
        
        # Validate Anthropic settings
        if self.anthropic.max_tokens <= 0:
            errors.append("ANTHROPIC_MAX_TOKENS must be greater than 0")
        
        if self.anthropic.temperature < 0 or self.anthropic.temperature > 1:
            errors.append("ANTHROPIC_TEMPERATURE must be between 0 and 1")
        
        if self.anthropic.timeout <= 0:
            errors.append("ANTHROPIC_TIMEOUT must be greater than 0")
        
        # Validate server settings
        if self.server.port <= 0 or self.server.port > 65535:
            errors.append("SERVER_PORT must be between 1 and 65535")
        
        return errors
    
    def get_environment_summary(self) -> Dict[str, Any]:
        """Get a summary of current environment configuration"""
        return {
            "redis": {
                "url": self.redis.url,
                "max_connections": self.redis.max_connections,
                "timeout": self.redis.socket_timeout
            },
            "cache": {
                "translation_ttl": self.cache.translation_ttl,
                "language_detection_ttl": self.cache.language_detection_ttl,
                "message_history_max": self.cache.message_history_max
            },
            "rate_limit": {
                "enabled": self.rate_limit.enabled,
                "max_requests": self.rate_limit.max_requests,
                "window_seconds": self.rate_limit.window_seconds
            },
            "anthropic": {
                "model": self.anthropic.model,
                "max_tokens": self.anthropic.max_tokens,
                "temperature": self.anthropic.temperature,
                "timeout": self.anthropic.timeout
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "debug": self.server.debug,
                "instance_id": self.server.instance_id
            },
            "logging": {
                "level": self.logging.level,
                "file_path": self.logging.file_path
            },
            "monitoring": {
                "enabled": self.monitoring.enabled,
                "stats_collection_interval": self.monitoring.stats_collection_interval,
                "retention_days": self.monitoring.retention_days
            }
        }

def setup_logging(config: LoggingConfig):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, config.level),
        format=config.format,
        handlers=[
            logging.StreamHandler(),
            *([logging.FileHandler(config.file_path)] if config.file_path else [])
        ]
    )
    
    # Set specific logger levels
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Global settings instance
settings = Settings()

# Validate settings on import
validation_errors = settings.validate()
if validation_errors:
    error_message = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
    logger.error(error_message)
    raise ValueError(error_message)

# Setup logging
setup_logging(settings.logging)

logger.info("Configuration loaded successfully")
logger.info(f"Environment summary: {settings.get_environment_summary()}")