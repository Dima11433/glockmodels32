import asyncio
import logging
from dataclasses import dataclass

import aiohttp
from aiocryptopay import AioCryptoPay, Networks

from db import Database

logger = logging.getLogger(__name__)

LEVELS = [(50, 15), (25, 10), (10, 5)]


def percent_for_clients(clients: int) -> int:
    for threshold, percent in LEVELS:
        if clients >= threshold:
            return percent
    return 0


class XRocketPay:
    """Интеграция с xRocket Pay API (https://pay.xrocket.tg)"""

    BASE_URL = "https://pay.xrocket.tg"

    def __init__(self, api_key: str):
        self.api_key = api_key.strip() if api_key else ""
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Rocket-Pay-Key": self.api_key}
            )
        return self._session

    async def create_invoice(self, amount_usd: float, description: str, currency: str = "USDT") -> tuple[int, str]:
        """Создание инвойса в xRocket. Возвращает (invoice_id, pay_link)"""
        session = await self._get_session()
        payload = {
            "amount": round(amount_usd, 2),
            "currency": currency,
            "description": description[:255],
            "numPayments": 1,
            "hidden": False,
        }
        url = f"{self.BASE_URL}/tg-invoices"
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if resp.status in (200, 201) and data.get("success"):
                inv_data = data["data"]
                inv_id = int(inv_data["id"])
                pay_link = inv_data.get("link") or inv_data.get("botUrl") or f"https://t.me/xrocket?start=mci_{inv_id}"
                return inv_id, pay_link
            else:
                err_msg = data.get("message") or str(data)
                logger.error(f"xRocket create_invoice error: {err_msg}")
                raise RuntimeError(f"xRocket error: {err_msg}")

    async def get_status(self, invoice_id: int) -> str:
        """Получение статуса инвойса xRocket ('paid', 'active', 'expired')"""
        session = await self._get_session()
        url = f"{self.BASE_URL}/tg-invoices/{invoice_id}"
        try:
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status in (200, 201) and data.get("success"):
                    inv_data = data["data"]
                    # Статусы в xRocket: 'paid', 'active', 'expired'
                    raw_status = str(inv_data.get("status", "")).lower()
                    if raw_status == "paid":
                        return "paid"
                    elif raw_status == "expired":
                        return "expired"
                    return "active"
                return "active"
        except Exception as e:
            logger.warning(f"xRocket get_status error for {invoice_id}: {e}")
            return "active"

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class Payments:
    def __init__(self, cryptopay_token: str = "", cryptopay_testnet: bool = False, xrocket_api_key: str = ""):
        self.crypto = None
        if cryptopay_token and cryptopay_token.strip():
            network = Networks.TEST_NET if cryptopay_testnet else Networks.MAIN_NET
            self.crypto = AioCryptoPay(token=cryptopay_token.strip(), network=network)

        self.xrocket = None
        if xrocket_api_key and xrocket_api_key.strip():
            self.xrocket = XRocketPay(api_key=xrocket_api_key.strip())

    @property
    def cryptopay_enabled(self) -> bool:
        return self.crypto is not None

    @property
    def xrocket_enabled(self) -> bool:
        return self.xrocket is not None and self.xrocket.enabled

    @property
    def enabled(self) -> bool:
        return self.cryptopay_enabled or self.xrocket_enabled

    async def create_invoice(self, amount_cents: int, description: str, provider: str = "cryptopay") -> tuple[int, str]:
        """Создает счет через выбранного провайдера (cryptopay или xrocket)."""
        amount_usd = amount_cents / 100

        if provider == "xrocket":
            if not self.xrocket_enabled:
                raise RuntimeError("xRocket payments are not configured")
            return await self.xrocket.create_invoice(amount_usd, description, currency="USDT")
        else:
            if not self.cryptopay_enabled:
                raise RuntimeError("CryptoPay is not configured")
            inv = await self.crypto.create_invoice(
                asset="USDT", amount=amount_usd, description=description, expires_in=1800
            )
            return inv.invoice_id, inv.bot_invoice_url

    async def get_statuses(self, invoices: list) -> dict[int, str]:
        """
        Проверяет статусы списка инвойсов.
        invoices: список dict/Row или ID (если передан список int — проверяет через CryptoPay).
        """
        result: dict[int, str] = {}
        crypto_ids = []
        xrocket_ids = []

        for item in invoices:
            if isinstance(item, (int, str)):
                crypto_ids.append(int(item))
            elif hasattr(item, "keys") or isinstance(item, dict):
                iid = int(item["invoice_id"])
                prov = str(item.get("provider", "cryptopay")).lower() if isinstance(item, dict) else (item["provider"] if "provider" in item.keys() else "cryptopay")
                if prov == "xrocket":
                    xrocket_ids.append(iid)
                else:
                    crypto_ids.append(iid)

        # Проверяем CryptoPay
        if crypto_ids and self.cryptopay_enabled:
            try:
                cp_invs = await self.crypto.get_invoices(invoice_ids=crypto_ids)
                if cp_invs:
                    if not isinstance(cp_invs, list):
                        cp_invs = [cp_invs]
                    for i in cp_invs:
                        result[i.invoice_id] = i.status
            except Exception as e:
                logger.warning(f"CryptoPay get_statuses error: {e}")

        # Проверяем xRocket
        if xrocket_ids and self.xrocket_enabled:
            for iid in xrocket_ids:
                try:
                    st = await self.xrocket.get_status(iid)
                    result[iid] = st
                except Exception as e:
                    logger.warning(f"xRocket get_status error for {iid}: {e}")

        return result

    async def close(self) -> None:
        if self.crypto:
            await self.crypto.close()
        if self.xrocket:
            await self.xrocket.close()


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
    purpose = inv["purpose"]
    if purpose == "topup":
        await db.add_balance(inv["user_id"], inv["amount"])
    elif purpose.startswith("ads_"):
        ad_type = purpose.replace("ads_", "")
        await db.conn.execute(
            "UPDATE ads_slots SET status = 'active' WHERE user_id = ? AND ad_type = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (inv["user_id"], ad_type)
        )
        await db.conn.commit()
    else:
        result.update(await db.fulfill_direct_purchase(inv))
    result["referral"] = await accrue_referral(db, inv["user_id"], inv["amount"], inv["purpose"])
    return result
