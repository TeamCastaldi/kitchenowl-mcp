from .config import get_settings


def get_token(request_context=None) -> str:
    # request_context is the v2 seam for per-user token mapping
    return get_settings().kitchenowl_api_token
