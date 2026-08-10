import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    test_bot_token: str | None
    cryptopay_token: str
    cryptopay_testnet: bool
    admin_username: str
    admin_group_id: int  # ID группы логирования


def load_config() -> Config:
    load_dotenv()
    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        test_bot_token=os.getenv("TEST_BOT_TOKEN", "").strip() or None,
        cryptopay_token=os.getenv("CRYPTOPAY_TOKEN", "").strip(),
        cryptopay_testnet=os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true",
        admin_username=os.getenv("ADMIN_USERNAME", "").strip().lstrip("@"),
        admin_group_id=-1004374620785,  # Админ группа для логов
    )
