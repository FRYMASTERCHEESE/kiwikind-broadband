from dataclasses import dataclass
from typing import Protocol

class SupplierNotConfigured(RuntimeError): pass

@dataclass(frozen=True)
class Availability:
    available: bool | None
    supplier_reference: str | None
    explanation: str

class WholesaleSupplier(Protocol):
    def check_address(self, address: str, postcode: str) -> Availability: ...
    def submit_order(self, order_id: str, accepted_quote_reference: str, idempotency_key: str) -> str: ...
    def get_order(self, supplier_reference: str) -> dict: ...
    def cancel_order(self, supplier_reference: str, idempotency_key: str) -> dict: ...
    def report_fault(self, service_reference: str, description: str, idempotency_key: str) -> str: ...

class UnconfiguredSupplier:
    def check_address(self, address, postcode):
        return Availability(None, None, 'Not checked: no contracted wholesale supplier is configured.')
    def submit_order(self, *args, **kwargs): raise SupplierNotConfigured('Live provisioning is disabled.')
    def get_order(self, *args, **kwargs): raise SupplierNotConfigured('No supplier connection.')
    def cancel_order(self, *args, **kwargs): raise SupplierNotConfigured('No supplier connection.')
    def report_fault(self, *args, **kwargs): raise SupplierNotConfigured('No supplier connection.')
