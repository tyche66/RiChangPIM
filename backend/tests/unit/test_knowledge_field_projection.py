from app.knowledge.field_projection import LevelProjectionStrategy
from app.knowledge.permission_pool import POOL_SALES


def test_projection_filters_hidden_fact_rows():
    payload = {
        'facts': [
            {'name': 'product_no', 'value': 'A100'},
            {'name': 'cost_price', 'value': 99},
            {'name': 'supplier_name', 'value': 'Secret'},
        ]
    }
    projected = LevelProjectionStrategy().project(payload, POOL_SALES)
    assert projected['facts'] == [{'name': 'product_no', 'value': 'A100'}]
