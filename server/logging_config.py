"""日志配置"""
import logging
import sys
from datetime import datetime


def setup_logging(log_level: str = "INFO"):
    """配置日志系统"""

    # 创建日志格式
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 配置根日志器
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/server_{datetime.now().strftime('%Y%m%d')}.log"),
        ],
    )

    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiortc").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# 创建日志器
logger = setup_logging()
