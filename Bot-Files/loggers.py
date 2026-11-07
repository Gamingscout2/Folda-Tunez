"""Rotating-file loggers for bot, CLI, and yt-dlp."""
import logging
from logging.handlers import RotatingFileHandler


def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


bot_logger = setup_logger('bot', 'bot.log')
cli_logger = setup_logger('cli', 'cli.log')
yt_logger  = setup_logger('yt_dlp', 'yt_dlp.log', level=logging.WARNING)