from __future__ import annotations

from storage.models import Metric

import logging

logger = logging.getLogger("storage.metrics")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)


def add_metric(session, run_id: int, scope: str, name: str, value):
    value_float = None
    value_int = None
    value_text = None
    value_json = None

    if isinstance(value, bool):
        value_int = int(value)
    elif isinstance(value, int):
        value_int = value
    elif isinstance(value, float):
        value_float = value
    elif isinstance(value, (dict, list)):
        value_json = value
    elif value is not None:
        value_text = str(value)

    metric = Metric(
        run_id=run_id,
        scope=scope,
        name=name,
        value_float=value_float,
        value_int=value_int,
        value_text=value_text,
        value_json=value_json,
    )
    session.add(metric)
    logger.info(f"Added metric: {scope}/{name} = {value} (int: {value_int}, float: {value_float}, text: {value_text}, json: {value_json})")
    session.commit()
