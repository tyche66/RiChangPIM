from app.api.v1.categories import router


def test_category_list_response_model_matches_envelope():
    route = next(route for route in router.routes if route.path == "" and "GET" in route.methods)
    assert route.response_model is dict
