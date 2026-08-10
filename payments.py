from aiocryptopay import AioCryptoPay, Networks

from db import Database

LEVELS = [(50, 15), (25, 10), (10, 5)]


def percent_for_clients(clients: int) -> int:
    for threshold, percent in LEVELS:
        if clients >= threshold:
            return percent
    return 0


class Payments:
    def __init__(self, token: str, testnet: bool = False):
        self.crypto = None
        if token:
            network = Networks.TEST_NET if testnet else Networks.MAIN_NET
            self.crypto = AioCryptoPay(token=token, network=network)

    @property
    def enabled(self) -> bool:
        return self.crypto is not None

    async def create_invoice(self, amount_cents: int, description: str) -> tuple[int, str]:
        inv = await self.crypto.create_invoice(
            asset="USDT", amount=amount_cents / 100, description=description, expires_in=1800)
        return inv.invoice_id, inv.bot_invoice_url

    async def get_statuses(self, invoice_ids: list[int]) -> dict[int, str]:
        invoices = await self.crypto.get_invoices(invoice_ids=invoice_ids)
        if invoices is None:
            return {}
        if not isinstance(invoices, list):
            invoices = [invoices]
        return {i.invoice_id: i.status for i in invoices}

    async def close(self) -> None:
        if self.crypto:
            await self.crypto.close()


async def accrue_referral(db: Database, payer_id: int, amount: int, source: str) -> dict | None:
    user = await db.get_user(payer_id)
    if not user or not user["referrer_id"]:
        return None
    referrer_id = user["referrer_id"]
    clients = await db.count_referral_clients(referrer_id)
    percent = percent_for_clients(clients)
    bonus = amount * percent // 100
    if bonus <= 0:
        return None
    await db.add_referral_earning(referrer_id, payer_id, bonus, percent, source)
    return {"referrer_id": referrer_id, "bonus": bonus, "percent": percent}


async def apply_paid_invoice(db: Database, inv) -> dict | None:
    if not await db.mark_invoice_paid(inv["invoice_id"]):
        return None
    result = {"purpose": inv["purpose"], "user_id": inv["user_id"], "amount": inv["amount"]}
    if inv["purpose"] == "topup":
        await db.add_balance(inv["user_id"], inv["amount"])
    else:
        result.update(await db.fulfill_direct_purchase(inv))
    result["referral"] = await accrue_referral(db, inv["user_id"], inv["amount"], inv["purpose"])
    return result
