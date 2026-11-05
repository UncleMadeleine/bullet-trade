import logging

from bullet_trade.core.globals import log
from bullet_trade.core.orders import LimitOrderStyle, clear_order_queue, order


def test_order_log_shows_limit_style_price(caplog):
    clear_order_queue()
    with caplog.at_level(logging.DEBUG, logger=log.logger.name):
        order("159915.XSHE", 30100, LimitOrderStyle(3.319))

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "创建订单: 159915.XSHE, 数量: 30100" in text
    assert "风格: LimitOrderStyle(price=3.3190)" in text
    assert "价格: 3.3190" in text
    assert "价格: None" not in text

    clear_order_queue()
