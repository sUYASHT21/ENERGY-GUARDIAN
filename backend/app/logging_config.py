import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_seg_configured", False):
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    root._seg_configured = True  # type: ignore[attr-defined]
