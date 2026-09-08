"""Petstore HTTP client for the Agentic Petstore onboarding project.

Re-exports the small public surface consumers (the MCP server, eventually)
are meant to import: the client itself, the domain models, and the
exception hierarchy. Nothing else in this package should be considered
public API.
Petstore Agentic 入门项目用的 Petstore HTTP 客户端。

这里重新导出了供下游消费者(以后是 MCP 服务器)使用的一小块公开接口:
客户端本身、领域模型、以及异常体系。这个包里除此以外的东西都不应该被
当作公开 API 使用。
"""

from pet_client.client import PetstoreClient
from pet_client.exceptions import (
    InvalidRequestError,
    PetNotAvailableError,
    PetNotFoundError,
    PetstoreClientError,
    PurchaseFailedError,
    StoreUnavailableError,
)
from pet_client.models import Availability, Order, Pet, PetSearch, PurchaseRequest, Species

__all__ = [
    "Availability",
    "InvalidRequestError",
    "Order",
    "Pet",
    "PetNotAvailableError",
    "PetNotFoundError",
    "PetSearch",
    "PetstoreClient",
    "PetstoreClientError",
    "PurchaseFailedError",
    "PurchaseRequest",
    "Species",
    "StoreUnavailableError",
]
