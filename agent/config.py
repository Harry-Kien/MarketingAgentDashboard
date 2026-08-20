"""Cấu hình tập trung. Mọi giá trị đọc từ .env, không hardcode ở nơi khác."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Nhà cung cấp model ---
    # vertex    = Claude qua Vertex AI (GCP ADC, không cần API key)
    # anthropic = Claude qua API trực tiếp của Anthropic (cần API key)
    # Cùng model, cùng giá. Đổi giá trị này là đổi đường đi, không đụng mã.
    llm_provider: str = "gemini"
    anthropic_api_key: str = ""

    # --- Vertex AI ---
    gcp_project_id: str = ""
    gcp_region: str = "global"          # cho Claude trên Vertex
    gemini_region: str = "us-central1"  # cho Gemini trên Vertex
    model_chat: str = "gemini-2.5-flash"
    model_hard: str = "gemini-2.5-pro"
    model_cheap: str = "gemini-2.5-flash-lite"

    # --- ZaloCRM ---
    zalocrm_base_url: str = "http://localhost:3000"
    zalocrm_api_key: str = ""
    webhook_public_url: str = "http://host.docker.internal:8000/webhook"
    webhook_secret: str = ""
    # Id tài khoản Zalo dùng để GỬI. Lấy sau khi quét QR:
    #   python -m scripts.zalo_link
    zalocrm_account_id: str = ""
    # Giây giữa hai lần hỏi ZaloCRM có tin mới (webhook bị chốt SSRF chặn).
    zalocrm_poll_seconds: float = 4.0
    # Kết nối CHỈ ĐỌC tới Postgres của ZaloCRM để liệt kê nick Zalo —
    # Public API không có endpoint nào làm việc này. Để rỗng thì tự dựng
    # chuỗi kết nối từ ZaloCRM/.env.
    zalocrm_db_url: str = ""

    # --- Chatwoot (hộp thư đa nền tảng) ---
    # Gom Facebook Messenger, Instagram DM, WhatsApp, khung chat website và
    # email về cùng một chỗ. Chatwoot KHÔNG chặn SSRF nên kênh này đi bằng
    # webhook thật, không phải polling như ZaloCRM.
    chatwoot_base_url: str = ""
    chatwoot_api_token: str = ""
    chatwoot_account_id: str = ""

    # --- Dữ liệu ---
    database_url: str = "postgresql://agent:agent@localhost:5433/marketing_agent"

    # --- TTS ---
    # auto = thử viet-tts trước, không có thì dùng Google Cloud TTS.
    # viettts | google = ép dùng đúng một nhà cung cấp.
    tts_provider: str = "auto"
    tts_base_url: str = "http://localhost:8298/v1"
    tts_voice: str = "nu-nhe-nhang"
    # Giọng Google Cloud TTS. Cần bật API trước (tính tiền theo ký tự):
    #   gcloud services enable texttospeech.googleapis.com
    google_tts_voice: str = "vi-VN-Neural2-A"

    # --- Video ---
    video_studio_dir: str = "./video-studio"
    video_output_dir: str = "./data/videos"
    ffprobe_bin: str = "ffprobe"
    # Bậc Veo TẮT theo mặc định. Veo tính tiền theo giây video sinh ra, nên
    # không được phép tự chạy chỉ vì có ảnh trong tay. Điền tên model (ví dụ
    # `veo-3.1-generate-preview`) mới bật.
    veo_model: str = ""
    # Bậc HyperFrames cũng TẮT theo mặc định, nhưng vì lý do khác Veo: nó
    # chưa dựng được lớp giọng đọc trong composition. Bật khi hình đẹp quan
    # trọng hơn tiếng, hoặc sau khi đã làm xong phần âm thanh cho nó.
    hyperframes_bat: bool = False
    # Số video dựng cùng lúc. Để 1: ffmpeg ăn CPU nặng, mà nó chạy chung
    # tiến trình với việc trả lời khách — việc trước mặt khách ưu tiên hơn.
    video_workers: int = 1

    # --- Phân phối nội dung lên mạng xã hội ---
    # Đường đi ưu tiên: n8n -> API chính thức -> hàng đợi thủ công.
    # n8n giữ OAuth của Facebook/TikTok, hệ thống này không giữ token dài hạn.
    n8n_webhook_url: str = ""
    n8n_auth_header: str = ""
    # URL mà n8n / Instagram gọi ngược lại được. Trong Docker Desktop phải
    # là host.docker.internal, không phải localhost.
    public_base_url: str = "http://host.docker.internal:8000"

    # Meta — để rỗng là tắt. Cần Business Verification + App Review.
    fb_page_id: str = ""
    fb_page_token: str = ""
    ig_user_id: str = ""

    # TikTok — để rỗng là tắt. Cần audit Content Posting API.
    # Chưa audit thì BẮT BUỘC để SELF_ONLY, đăng public sẽ bị từ chối.
    tiktok_access_token: str = ""
    tiktok_privacy: str = "SELF_ONLY"

    # Bài đăng KHÔNG BAO GIỜ tự đi khi chưa có người duyệt. Đổi thành true
    # là chấp nhận rủi ro đăng nội dung sai lên trang thật.
    tu_dong_dang_khong_can_duyet: bool = False

    # --- Langfuse ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # --- Vận hành ---
    agent_enabled: bool = True
    agent_mode: str = "assist"          # assist | auto
    # Tách câu trả lời dài thành 2-3 tin và nghỉ giữa các tin đúng khoảng
    # thời gian gõ. Tắt đi thì gửi một cục, nhanh hơn nhưng lộ máy ngay.
    nhip_nguoi_that: bool = True
    confidence_floor: float = 0.55
    max_cost_per_conversation: float = 0.25
    # Đơn từ mức này trở lên KHÔNG được agent tự chốt — vào hàng chờ duyệt.
    nguong_tu_chot_vnd: int = 1_000_000

    @property
    def studio_path(self) -> Path:
        p = Path(self.video_studio_dir)
        return p if p.is_absolute() else ROOT / p

    @property
    def video_out_path(self) -> Path:
        p = Path(self.video_output_dir)
        p = p if p.is_absolute() else ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def langfuse_on(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
