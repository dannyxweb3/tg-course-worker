"""集中配置。所有敏感项走 .env，不进代码库。

多频道之后，bot token / 频道 id 这些**不再放在这里**，而是存库（token 只存
环境变量名）。这里只留全局设置和引导用的默认值。
"""
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MEDIA_DIR = DATA_DIR / "media"
LOG_DIR = ROOT / "logs"
PROMPT_DIR = ROOT / "config" / "prompts"
WEB_DIR = ROOT / "app" / "web"

for _d in (DATA_DIR, MEDIA_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# botpool 要按库里存的 token_env_key 去 os.environ 里取任意变量名，
# 所以 .env 必须真的加载进环境，不能只喂给 pydantic。
load_dotenv(ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # 我们有 model_classify / model_generate 等字段，与 pydantic 的
        # model_ 保留前缀撞名，关掉该检查
        protected_namespaces=(),
    )

    # ---- 你自己 ----
    owner_id: int

    # ---- LLM ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    model_classify: str = "deepseek-chat"
    model_generate: str = "deepseek-chat"
    model_rewrite: str = "deepseek-reasoner"

    # ---- 全局默认（新建频道时的初始值）----
    timezone: str = "Asia/Shanghai"
    default_publish_cron: str = "0 9 * * *"
    relevance_threshold: int = 5
    queue_low_watermark: int = 3
    health_check_hour: int = 8

    # ---- 资料仓库频道 ----
    # 一个私有频道，生产 bot 和所有售卖 bot 都要是它的管理员。
    # 文件先 copy 进这里，发货时再从这里 copy 给读者——file_id 是绑 bot 的，
    # 生产 bot 拿到的 file_id 售卖 bot 用不了，只能靠这个频道中转。
    vault_channel_id: int = 0

    # ---- 管理后台 ----
    web_enabled: bool = True
    # 默认只绑本机：通过 SSH 隧道访问，不需要域名/证书/反代，
    # 也就没有公网入口可以被扫。要对外暴露请自己加反代 + HTTPS。
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    web_password: str = ""
    web_secret: str = ""

    # ---- 引导用（scripts/bootstrap.py 读，之后就不再用了）----
    producer_bot_token: str = ""
    sale_bot_token: str = ""
    channel_id: int = 0
    channel_name: str = "主频道"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def web_url(self) -> str:
        """后台地址，用在 bot 发给你的提示里。绑 0.0.0.0 时按本机地址显示，
        免得提示里出现点不开的 http://0.0.0.0:8080。
        """
        host = "127.0.0.1" if self.web_host in ("0.0.0.0", "::") else self.web_host
        return f"http://{host}:{self.web_port}"

    @property
    def db_path(self) -> Path:
        return DATA_DIR / "worker.db"


settings = Settings()  # type: ignore[call-arg]
