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
    # openai    = OpenAI API trực tiếp (gpt-4o-mini, gpt-4o)
    # vertex    = Claude qua Vertex AI (GCP ADC, không cần API key)
    # anthropic = Claude qua API trực tiếp của Anthropic (cần API key)
    # gemini    = Gemini trên Vertex AI
    # Cùng model, cùng giá. Đổi giá trị này là đổi đường đi, không đụng mã.
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""

    # --- Vertex AI ---
    gcp_project_id: str = ""
    gcp_region: str = "global"          # cho Claude trên Vertex
    gemini_region: str = "us-central1"  # cho Gemini trên Vertex
    model_chat: str = "gpt-4o-mini"
    model_hard: str = "gpt-4o"
    model_cheap: str = "gpt-4o-mini"

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
    chatwoot_webhook_secret: str = ""

    # --- Zalo OA (cổng chính thức, GĐ2) ---
    # Dựng sẵn và TẮT: thiếu ba khoá dưới thì registry không bật kênh. Đây
    # là đường đúng để thay Zalo cá nhân — nick cá nhân vi phạm điều khoản
    # Zalo, và khoá nick là mất luôn lịch sử hội thoại với khách.
    zalo_oa_app_id: str = ""
    zalo_oa_secret_key: str = ""
    # Chỉ là hạt giống cho lần làm mới ĐẦU TIÊN. Zalo xoay vòng refresh
    # token mỗi lần đổi, nên bản đang dùng nằm ở bảng `zalo_oa_token` trong
    # CSDL — máy tự ghi mỗi giờ, không phải thứ người sửa tay trong .env.
    zalo_oa_refresh_token: str = ""
    zalo_oa_api_base: str = "https://openapi.zalo.me/v3.0/oa"
    zalo_oa_oauth_url: str = "https://oauth.zaloapp.com/v4/oa/access_token"
    # Cửa sổ được nhắn tự do, tính từ tin CUỐI của khách. Để trong cấu hình
    # chứ không gõ vào mã vì Zalo đã đổi con số này ít nhất một lần — và
    # một hằng số sai nằm trong mã thì phải sửa mã mới chữa được.
    # 0 = tắt phép kiểm, CHỈ dùng khi thử.
    zalo_oa_cua_so_gio: float = 168.0     # 7 ngày

    # --- Facebook Messenger (nối THẲNG, không qua Chatwoot) ---
    # Đường thứ hai tới Messenger, cùng tồn tại với Chatwoot có chủ ý: đi
    # thẳng thì bớt một Rails + một Postgres + một Redis phải nuôi, đi qua
    # Chatwoot thì được hộp thư gộp cho người trực. Chọn theo việc.
    # KHÔNG bỏ qua được App Review của Meta — đó là luật của họ, không phải
    # hệ quả kiến trúc.
    messenger_page_id: str = ""
    # App ID của chính app này. Dùng để nhận ra 'nhân viên đã xong,
    # quyền vừa được trả về cho ta' trong sự kiện pass_thread_control.
    messenger_app_id: str = ""
    messenger_page_token: str = ""        # Page access token dài hạn
    messenger_app_secret: str = ""        # ký X-Hub-Signature-256
    messenger_verify_token: str = ""      # dội lại hub.challenge lần bắt tay
    messenger_api_base: str = "https://graph.facebook.com/v21.0"
    # Cửa sổ tiêu chuẩn của Meta, tính từ tin CUỐI của khách. Ngoài cửa sổ
    # phải dùng Message Tag hoặc quảng cáo — cơ chế khác, không phải việc
    # của adapter. 0 = tắt phép kiểm, CHỈ dùng khi thử.
    messenger_cua_so_gio: float = 24.0

    # --- Vận chuyển (GHN / GHTK / Mock) ---
    shipping_provider: str = "mock"
    ghn_api_url: str = "https://online-gateway.ghn.vn/shiip/public-api/v2"
    ghn_token: str = ""
    ghn_shop_id: str = ""
    shipping_webhook_secret: str = ""

    # --- Quản trị Doanh nghiệp ERP (nexterp / mock / internal) ---
    erp_provider: str = "nexterp"
    nexterp_base_url: str = "http://localhost:8080"
    nexterp_api_key: str = ""
    nexterp_api_secret: str = ""
    erp_cache_ttl_seconds: int = 300

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

    # --- Sao lưu ---
    # Mất dữ liệu là loại hỏng DUY NHẤT trong hệ thống này không sửa được
    # sau, nên mặc định BẬT. Bản sao nằm ở data/backup, không lên repo.
    sao_luu_moi_ngay: bool = True
    sao_luu_giu_lai: int = 14

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

    # --- Bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP) ---
    # Điều 16: dữ liệu chỉ được lưu trong thời hạn phù hợp với mục đích đã
    # thông báo. 180 ngày là mức hợp lý cho mục đích chăm sóc khách hàng:
    # đủ dài để tra lại lịch sử tư vấn, đủ ngắn để không giữ vô thời hạn.
    # KHÔNG áp cho đơn hàng — chứng từ kế toán có thời hạn riêng dài hơn
    # nhiều (Luật Kế toán 2015, Điều 41).
    luu_hoi_thoai_ngay: int = 180
    # Tự dọn dữ liệu quá hạn mỗi ngày. Tắt thì phải tự bấm trên dashboard.
    tu_dong_don_du_lieu: bool = True

    # --- Canh gác ---
    # Hỏi sức khoẻ đều đặn và báo khi trạng thái ĐỔI sang hỏng. Báo mỗi lần
    # kiểm thì sau nửa tiếng người ta tắt thông báo, và lần hỏng thật tiếp
    # theo không ai đọc.
    canh_gac_bat: bool = True
    canh_gac_moi_giay: int = 300
    # Nơi nhận báo động. Đi qua webhook chứ không gửi thẳng Zalo hay email:
    # nơi nhận là việc của doanh nghiệp, và n8n đã chạy sẵn để định tuyến.
    # Để rỗng thì chỉ ghi vào nhật ký.
    canh_gac_webhook: str = ""
    # Khách đã được chuyển cho người mà chờ quá số phút này thì canh gác
    # báo động. Đây là phép kiểm DUY NHẤT hướng ra phía khách: tám phép
    # còn lại hỏi "hệ thống có sống không", phép này hỏi "có ai đang bị bỏ
    # quên không". Hệ thống sống nguyên vẹn mà khách ngồi chờ hai tiếng thì
    # vẫn là hỏng, chỉ là hỏng ở phía không có mã nào chạy.
    cho_nguoi_toi_da_phut: int = 30

    # --- Vận hành ---
    agent_enabled: bool = True
    agent_mode: str = "assist"          # assist | auto
    # Tách câu trả lời dài thành 2-3 tin và nghỉ giữa các tin đúng khoảng
    # thời gian gõ. Tắt đi thì gửi một cục, nhanh hơn nhưng lộ máy ngay.
    nhip_nguoi_that: bool = True
    # Câu báo cho khách khi agent chuyển người. CỐ ĐỊNH, không phải lời
    # model sinh ra: lúc chuyển người là lúc agent đã tự nhận không đủ thẩm
    # quyền, nên đó chính là lúc KHÔNG nên để nó tự chọn chữ.
    tin_chuyen_nguoi: str = (
        "Dạ phần này em nhờ bạn có chuyên môn bên em hỗ trợ mình cho chắc "
        "ạ. Bạn ấy sẽ nhắn lại cho mình sớm nhé."
    )
    # Ngoài giờ trực, câu trên là một lời nói dối: không ai đang ngồi đó, và
    # "sớm" nghĩa là sáu tiếng nữa. Cả hệ thống được xây quanh nguyên tắc
    # không phát ngôn không có căn cứ; đây là chỗ hở cuối cùng trong nguyên
    # tắc đó. Nói rõ mấy giờ có người thì khách chờ được — không nói thì
    # khách bỏ đi.
    gio_lam_viec_bat: bool = True
    gio_lam_viec_bat_dau: int = 8       # giờ Việt Nam, UTC+7
    gio_lam_viec_ket_thuc: int = 21     # 20:59 còn trong giờ, 21:00 thì hết
    tin_chuyen_nguoi_ngoai_gio: str = (
        "Dạ phần này em nhờ bạn có chuyên môn bên em hỗ trợ mình cho chắc ạ. "
        "Giờ này bên em ngoài giờ làm việc rồi, bạn ấy sẽ nhắn lại cho mình "
        "từ {gio_mo} sáng mai nhé."
    )
    # Cookie phiên chỉ gửi qua HTTPS. Bật cứng thì đăng nhập trên
    # http://localhost hỏng, nên để theo cấu hình — và BẮT BUỘC bật khi
    # đưa lên server thật.
    # --- MCP qua HTTP ---
    # Đặt token là BẬT; để rỗng là TẮT hẳn. Fail-closed có chủ đích: máy chủ
    # MCP mở ra toàn bộ danh mục, đơn hàng và kho tri thức cho bất kỳ client
    # nào gọi được. Một tính năng như vậy không được bật theo mặc định chỉ
    # vì nó tiện.
    #
    # Sinh token: python -c "import secrets; print(secrets.token_urlsafe(32))"
    mcp_token: str = ""

    cookie_bao_mat: bool = False
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
