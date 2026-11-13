"""Client sinh từ OpenAPI cần operationId duy nhất cho từng thao tác."""
import warnings

from fastapi import FastAPI

from agent.api import tich_hop


def test_proxy_khong_sinh_operation_id_trung():
    app = FastAPI()
    app.include_router(tich_hop.router)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        schema = app.openapi()
    ids = [op["operationId"] for p in schema["paths"].values() for op in p.values()
           if isinstance(op, dict) and "operationId" in op]
    assert len(ids) == len(set(ids))
