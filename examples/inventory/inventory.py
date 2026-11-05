from dataclasses import dataclass


@dataclass
class Inventory:
    stock: int

    def reserve(self, quantity: int) -> None:
        if quantity > self.stock:
            raise ValueError("insufficient stock")
        self.stock -= quantity
