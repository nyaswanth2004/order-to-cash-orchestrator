"""JSON-file backed reference data (customers, products) with in-memory caching."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, TypeVar

from models.schemas import Customer, Product

logger = logging.getLogger(__name__)

T = TypeVar("T", Customer, Product)


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._customers: list[Customer] = []
        self._products: list[Product] = []
        self.reload()

    def reload(self) -> None:
        self._customers = self._read("customers.json", "customers", Customer)
        self._products = self._read("inventory.json", "products", Product)
        logger.info(
            "DataStore loaded %d customers and %d products from %s",
            len(self._customers),
            len(self._products),
            self._data_dir,
        )

    @property
    def customers(self) -> list[Customer]:
        return list(self._customers)

    @property
    def products(self) -> list[Product]:
        return list(self._products)

    def find_customer(self, query: str) -> Optional[Customer]:
        needle = query.strip().lower()
        for customer in self._customers:
            if needle in {customer.name.lower(), customer.customer_id.lower()}:
                return customer
        return None

    def find_product(self, query: str) -> Optional[Product]:
        needle = query.strip().lower()
        for product in self._products:
            if needle in {product.name.lower(), product.sku.lower()}:
                return product
        return None

    def _read(self, filename: str, key: str, model: type[T]) -> list[T]:
        path = self._data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Required data file is missing: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw[key] if isinstance(raw, dict) else raw
        parsed = [model.model_validate(item) for item in records]
        if not parsed:
            raise ValueError(f"Data file {path} contains no records")
        return parsed
