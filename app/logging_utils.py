import logging
import sys

from pythonjsonlogger import jsonlogger

from app.config import get_settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('ts'):
            # Use 'timestamp' from record if available (standard), else now
            from datetime import datetime
            log_record['ts'] = datetime.utcnow().isoformat() + 'Z'
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname

def setup_logging():
    settings = get_settings()
    log_level = settings.LOG_LEVEL.upper()
    
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter('%(ts)s %(level)s %(name)s %(message)s')
    logHandler.setFormatter(formatter)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    logger.addHandler(logHandler)
    
    # Set level for libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING) 
    # Suppress default uvicorn access logs to avoid double logging
    
    return logger

logger = setup_logging()
