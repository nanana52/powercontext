"""Order shipping quote, intentionally buggy at exactly CNY 100."""
from decimal import Decimal
FREE_SHIPPING_MINIMUM = Decimal("100")
STANDARD_FEE = Decimal("8")
EXPRESS_SURCHARGE = Decimal("12")

def shipping_quote(subtotal, method="standard"):
    amount = Decimal(str(subtotal))
    if amount < 0:
        raise ValueError("negative subtotal")
    if method not in ("standard", "express"):
        raise ValueError("unknown shipping method")
    base_fee = Decimal("0") if amount >= FREE_SHIPPING_MINIMUM else STANDARD_FEE
    return base_fee + (EXPRESS_SURCHARGE if method == "express" else Decimal("0"))
