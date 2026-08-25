import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    test_bot_token: str | None
    cryptopay_token: str
    cryptopay_testnet: bool
    xrocket_api_key: str
    admin_username: str
    admin_group_id: int  # ID группы логирования
    update_channel_id: int  # ID канала для автопостинга обновлений
    bot_username: str  # Юзернейм бота


def load_config() -> Config:
    load_dotenv()
    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        test_bot_token=os.getenv("TEST_BOT_TOKEN", "").strip() or None,
        cryptopay_token=os.getenv("CRYPTOPAY_TOKEN", "").strip(),
        cryptopay_testnet=os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true",
        xrocket_api_key=os.getenv("XROCKET_API_KEY", "").strip(),
        admin_username=os.getenv("ADMIN_USERNAME", "").strip().lstrip("@"),
        admin_group_id=int(os.getenv("ADMIN_GROUP_ID", "-1004374620785")),
        update_channel_id=int(os.getenv("UPDATE_CHANNEL_ID", "-1004437922263")),
        bot_username=os.getenv("BOT_USERNAME", "glock_models_bot").strip().lstrip("@"),
    )
