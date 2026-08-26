"""
Kết nối Facebook / Instagram bằng ĐĂNG NHẬP, không phải dán token.

VÌ SAO LỚP NÀY TỒN TẠI
----------------------
Cách cũ: người vận hành mở Meta Dashboard, tìm App Secret, tìm đúng Trang,
bấm Generate Token, copy chuỗi 200 ký tự, quay lại dashboard dán vào đúng ô
— rồi lặp lại cho từng Trang.

Sáu thao tác và bốn chỗ có thể sai cho MỖI Trang. Và sai không nổ:
credential vẫn được mã hoá và lưu, tài khoản vẫn hiện trên dashboard, chỉ
có tin khách là không bao giờ tới. Có thể nhiều ngày sau mới ai đó nhận ra.

OAuth đổi chuyện đó thành: bấm một nút, chọn Trang, xong. Token đi thẳng từ
Meta vào vault và KHÔNG BAO GIỜ hiện trên màn hình.

RANH GIỚI BÍ MẬT
----------------
`app_secret` chỉ dùng ở bước đổi code lấy token, chạy phía máy chủ. Nó
KHÔNG BAO GIỜ được đưa vào URL trình duyệt — URL nằm trong lịch sử duyệt
web, trong log proxy, và trong ảnh chụp màn hình.
"""
from __future__ import annotations

import secrets
import time
import urllib.parse
from typing import Any

# Quyền tối thiểu để nhận và trả lời tin nhắn Trang.
#
# Thiếu `pages_messaging` là nối xong nhưng không nhắn được — và lỗi ấy chỉ
# lộ ra đúng lúc khách nhắn tới. Xin dư quyền cũng không tốt: App Review khó
# qua hơn, và người dùng thấy màn hình cấp quyền dài thì ngần ngại.
QUYEN = (
    "pages_show_list",        # liệt kê Trang người dùng quản lý
    "pages_messaging",        # nhận và gửi tin nhắn
    "pages_manage_metadata",  # đăng ký webhook cho Trang
    "instagram_basic",        # đọc tài khoản Instagram liên kết Trang
    "instagram_manage_messages",
)

# Phiên bản Graph API dùng cho luồng OAuth. Ghim tường minh: Meta ngừng hỗ
# trợ phiên bản cũ theo lịch, và một URL không ghi phiên bản sẽ lặng lẽ
# nhảy sang bản mới nhất — đổi hành vi mà không ai đổi mã.
GRAPH_VERSION = "v21.0"

# Đủ lâu để người dùng đọc màn hình cấp quyền của Meta, đủ ngắn để một
# `state` bị lộ không dùng lại được sau đó.
STATE_SONG_GIAY = 600

# Phiếu chọn Trang sống lâu hơn `state`: người dùng phải ĐỌC danh sách 26
# Trang rồi mới tick, và đọc thì lâu hơn bấm một nút cấp quyền.
PHIEU_SONG_GIAY = 1800


def dung_url_dang_nhap(*, app_id: str, redirect_uri: str, state: str) -> str:
    """
    URL màn hình cấp quyền của Meta.

    Người dùng NHÌN THẤY url này, nên nó chỉ được chứa thứ công khai: app id,
    địa chỉ quay về, quyền xin, và `state`. Không có app secret.
    """
    tham_so = urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": ",".join(QUYEN),
    })
    return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?{tham_so}"


class KhoState:
    """
    Giữ `state` của các lượt đăng nhập đang dở.

    VÌ SAO CẦN `state`
    ------------------
    Không có nó, kẻ khác dụ được quản trị viên mở một link callback đã dựng
    sẵn, và hệ thống sẽ nối MỘT TRANG CỦA CHÚNG vào — rồi tin nhắn khách của
    bạn đi qua tài khoản của người lạ. Đó là CSRF, và OAuth sinh ra `state`
    đúng để chặn nó.

    DÙNG MỘT LẦN RỒI BỎ
    -------------------
    Callback phát lại lần hai không được nối thêm tài khoản nữa.

    Giữ trong bộ nhớ tiến trình là ĐỦ cho luồng này: một lượt đăng nhập kéo
    dài chưa tới một phút, và khởi động lại giữa chừng thì người dùng chỉ
    cần bấm lại nút. Khác với nonce chống replay của sidecar — cái đó phải
    bền, vì nó canh cả những request tự động chạy 24/7.
    """

    def __init__(self) -> None:
        # state -> (hạn dùng, id người đã bấm nút)
        self._cho: dict[str, tuple[float, Any]] = {}

    def tao(self, user_id: Any) -> str:
        """
        Sinh state và NHỚ ai đã bấm nút.

        Callback không có phiên đăng nhập — Meta gọi vào và không mang cookie
        của ta. Nhưng tài khoản tạo ra vẫn phải ghi đúng người thao tác:
        `account_memberships.user_id` có khoá ngoại tới `nguoi_dung`, nên một
        id bịa làm cả lượt tạo thất bại.

        Và kể cả nếu không có khoá ngoại, ghi sai người vẫn làm nhật ký kiểm
        toán mất nghĩa — không ai truy được ai đã nối Trang nào.
        """
        self._don()
        s = secrets.token_urlsafe(32)
        self._cho[s] = (time.time() + STATE_SONG_GIAY, user_id)
        return s

    def dung(self, state: str):
        """
        Trả id người đã bấm nút nếu state hợp lệ, None nếu không.

        Gọi lần thứ hai với cùng state luôn trả None.
        """
        self._don()
        muc = self._cho.pop(str(state or ""), None)
        if muc is None:
            return None
        han, user_id = muc
        return user_id if han >= time.time() else None

    def _don(self) -> None:
        bay_gio = time.time()
        for s, (han, _ai) in list(self._cho.items()):
            if han < bay_gio:
                self._cho.pop(s, None)


class KhoChonTrang:
    """
    Giữ danh sách Trang giữa lúc hiện ra cho chọn và lúc người dùng bấm Lưu.

    VÌ SAO PHẢI GIỮ PHÍA MÁY CHỦ
    ----------------------------
    Danh sách kèm Page access token của TỪNG Trang. Muốn cho chọn thì phải
    hiện danh sách ra — nhưng chỉ hiện TÊN. Token nằm lại đây; trình duyệt
    chỉ gửi về những id đã tick.

    Đưa token vào HTML là đưa nó vào lịch sử trình duyệt, vào ảnh chụp màn
    hình người ta gửi cho nhau khi hỏi han, và vào mọi tiện ích mở rộng đang
    chạy trên tab đó.

    DÙNG MỘT LẦN, CÓ HẠN
    --------------------
    Cùng lý do với `KhoState`: phát lại không được nối thêm lần nữa. Giữ
    trong bộ nhớ tiến trình là đủ — khởi động lại giữa chừng thì người dùng
    bấm lại nút Kết nối, mất vài giây chứ không mất gì.
    """

    def __init__(self) -> None:
        # phiếu -> (hạn dùng, id người bấm, danh sách Trang kèm token)
        self._cho: dict[str, tuple[float, Any, list[dict]]] = {}

    def tao(self, user_id: Any, danh_sach: list[dict]) -> str:
        self._don()
        phieu = secrets.token_urlsafe(32)
        self._cho[phieu] = (time.time() + PHIEU_SONG_GIAY, user_id, danh_sach)
        return phieu

    def dung(self, phieu: str):
        """Trả `(người bấm, danh sách Trang)` nếu phiếu còn hiệu lực."""
        self._don()
        muc = self._cho.pop(str(phieu or ""), None)
        if muc is None:
            return None
        han, user_id, danh_sach = muc
        return (user_id, danh_sach) if han >= time.time() else None

    def _don(self) -> None:
        bay_gio = time.time()
        for k, (han, _ai, _ds) in list(self._cho.items()):
            if han < bay_gio:
                self._cho.pop(k, None)


_kho_chon = KhoChonTrang()


def _thoat(chu: Any) -> str:
    """
    Thoát ký tự HTML.

    Tên Trang do người ngoài đặt. Không thoát thì một Trang tên
    `<script>...</script>` chạy được mã trong trình duyệt của quản trị viên
    đang đăng nhập — và phiên đó có quyền đọc PII khách hàng.
    """
    return (str(chu)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def dung_trang_chon(phieu: str, danh_sach: list[dict]) -> str:
    """
    Màn hình chọn Trang. CHỈ hiện tên — không hiện token nào.

    Mặc định KHÔNG tick sẵn ô nào: nối một Trang là nhận trách nhiệm trả lời
    khách trên Trang đó, nên nó phải là một lựa chọn có ý thức. Tick sẵn tất
    cả rồi để người dùng bỏ bớt là cách chắc chắn nhất để họ bấm Lưu ngay và
    nối nhầm 26 Trang.
    """
    dong = []
    for trang in danh_sach:
        ig = ""
        if trang.get("instagram_id"):
            ten_ig = trang.get("instagram_username") or "tài khoản Instagram"
            ig = f'<span class="ig">+ Instagram @{_thoat(ten_ig)}</span>'
        dong.append(
            '<label class="muc">'
            f'<input type="checkbox" name="trang" value="{_thoat(trang["id"])}">'
            f'<span class="ten">{_thoat(trang.get("name") or trang["id"])}</span>'
            f'<span class="ma">{_thoat(trang["id"])}</span>{ig}</label>'
        )

    return (
        f'<p>Tài khoản Facebook của bạn quản lý <b>{len(danh_sach)} Trang</b>. '
        "Chọn những Trang bạn muốn agent chăm sóc khách hàng.</p>"
        "<p class=\"luu-y\">Chỉ chọn Trang đúng ngành hàng agent đang được "
        "nạp kiến thức. Nối một Trang lạ nghĩa là khách nhắn vào đó sẽ nhận "
        "câu trả lời sai lĩnh vực.</p>"
        '<form method="post" action="/api/connect/meta/chon">'
        f'<input type="hidden" name="phieu" value="{_thoat(phieu)}">'
        '<div class="thanh-cong-cu">'
        '<button type="button" id="tat-ca">Chọn tất cả</button>'
        '<button type="button" id="bo-het">Bỏ chọn hết</button></div>'
        f'<div class="ds">{"".join(dong)}</div>'
        '<button type="submit" class="chinh">Kết nối những Trang đã chọn</button>'
        "</form>"
        "<script>"
        "document.getElementById('tat-ca').onclick=function(){"
        "document.querySelectorAll('input[name=trang]').forEach(function(o){o.checked=true})};"
        "document.getElementById('bo-het').onclick=function(){"
        "document.querySelectorAll('input[name=trang]').forEach(function(o){o.checked=false})};"
        "</script>"
    )


def doc_trang_tu_me_accounts(phan_hoi: dict[str, Any]) -> list[dict]:
    """
    Danh sách Trang nhắn tin được, đọc từ phản hồi `/me/accounts`.

    BỎ TRANG KHÔNG CÓ QUYỀN NHẮN TIN
    --------------------------------
    Trang thiếu `MESSAGING` thì nối vào cũng không nhận được tin. Hiện nó
    trong danh sách chọn là mời người dùng phạm sai lầm, rồi phải tự hỏi vì
    sao Trang đó im lặng — mà không có gì trong hệ thống nói ra lý do.

    Thà danh sách ngắn hơn và mọi dòng trong đó đều dùng được.
    """
    ra: list[dict] = []
    for muc in (phan_hoi or {}).get("data") or []:
        if not isinstance(muc, dict):
            continue
        token = str(muc.get("access_token") or "")
        ma = str(muc.get("id") or "")
        if not token or not ma:
            continue
        viec = {str(t).upper() for t in (muc.get("tasks") or [])}
        if viec and "MESSAGING" not in viec:
            continue
        # Instagram Business luôn gắn với một Trang. Graph có khi trả `null`,
        # có khi trả kiểu khác — một Trang dữ liệu lạ không được làm hỏng 25
        # Trang còn lại.
        ig = muc.get("instagram_business_account")
        ig = ig if isinstance(ig, dict) else {}

        ra.append({
            "id": ma,
            "name": str(muc.get("name") or f"Trang {ma}"),
            "access_token": token,
            "instagram_id": str(ig.get("id") or ""),
            "instagram_username": str(ig.get("username") or ""),
        })
    return ra


# ---------------------------------------------------------------
#  Nối vào HTTP
# ---------------------------------------------------------------
import httpx  # noqa: E402
from fastapi import APIRouter, Depends, HTTPException, Query, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

from agent import db  # noqa: E402
from agent.config import settings  # noqa: E402

from .routes import bat_buoc_quan_tri  # noqa: E402

router = APIRouter(prefix="/api/connect/meta", tags=["oauth-meta"])

_KHO_STATE = KhoState()


def _app_id_va_secret() -> tuple[str, str]:
    app_id = settings.meta_app_id or settings.messenger_app_id
    app_secret = settings.meta_app_secret or settings.messenger_app_secret
    if not app_id or not app_secret:
        raise HTTPException(
            503,
            "Chưa cấu hình META_APP_ID và META_APP_SECRET trong .env. Đây là "
            "thông tin của ỨNG DỤNG Meta, khác token của từng Trang.",
        )
    return app_id, app_secret


def _dia_chi_quay_ve() -> str:
    goc = (settings.public_base_url or "").rstrip("/")
    if not goc.startswith("https://"):
        raise HTTPException(
            503,
            "Meta chỉ chấp nhận địa chỉ quay về dùng HTTPS. Dựng tunnel hoặc "
            "tên miền trước, rồi đặt PUBLIC_BASE_URL trỏ vào đó.",
        )
    return goc + "/api/connect/meta/callback"


@router.get("/start")
async def meta_start(user: dict = Depends(bat_buoc_quan_tri)) -> dict:
    """
    Trả về địa chỉ màn hình cấp quyền của Meta để dashboard mở ra.

    Không tự chuyển hướng: dashboard mở nó trong cửa sổ mới và giữ nguyên
    trang hiện tại, để lúc quay về người dùng không mất ngữ cảnh.
    """
    app_id, _bo_qua = _app_id_va_secret()
    return {
        "url": dung_url_dang_nhap(
            app_id=app_id,
            redirect_uri=_dia_chi_quay_ve(),
            state=_KHO_STATE.tao(user["id"]),
        )
    }


_CSS_TRANG = (
    "body{font:15px system-ui;padding:32px;max-width:46rem;margin:auto;"
    "line-height:1.6;color:#111}"
    ".luu-y{background:#fff7ed;border-left:3px solid #f59e0b;padding:10px 14px;"
    "border-radius:4px;font-size:14px}"
    ".thanh-cong-cu{display:flex;gap:8px;margin:14px 0 10px}"
    ".thanh-cong-cu button{padding:5px 12px;border:1px solid #d4d4d8;"
    "background:#fff;border-radius:6px;cursor:pointer;font-size:13px}"
    ".ds{border:1px solid #e4e4e7;border-radius:8px;max-height:52vh;"
    "overflow:auto}"
    ".muc{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;"
    "align-items:center;padding:11px 14px;border-bottom:1px solid #f1f1f4;"
    "cursor:pointer}"
    ".muc:last-child{border-bottom:0}"
    ".muc:hover{background:#fafafa}"
    ".muc input{width:17px;height:17px;grid-row:span 2}"
    ".ten{font-weight:600}"
    ".ma{font:12px ui-monospace,monospace;color:#71717a}"
    ".ig{grid-column:2;font-size:12.5px;color:#c026d3}"
    "button.chinh{margin-top:16px;padding:11px 20px;border:0;border-radius:8px;"
    "background:#111;color:#fff;font-size:15px;cursor:pointer}"
)


def _trang_ket_qua(tieu_de: str, than: str, *, tu_dong_lam_moi: bool = True
                   ) -> HTMLResponse:
    """
    Trang Meta quay về. Mở trong cửa sổ mới nên phải tự đóng lại được.

    KHÔNG in token, mã lỗi thô hay giá trị nhạy cảm nào ra đây — người dùng
    hay chụp màn hình trang này để hỏi.

    `tu_dong_lam_moi=False` cho màn hình CHỌN Trang: ở đó việc chưa xong, và
    làm mới dashboard phía sau lúc người ta đang tick là vừa vô nghĩa vừa gây
    hiểu nhầm rằng đã lưu.
    """
    duoi = (
        "<p><button onclick='window.close()'>Đóng cửa sổ này</button></p>"
        "<script>setTimeout(function(){try{"
        "window.opener&&window.opener.location.reload()}catch(e){}},500)</script>"
    ) if tu_dong_lam_moi else ""

    khung = (
        "<!doctype html><meta charset='utf-8'>"
        "<style>" + _CSS_TRANG + "</style>"
        "<h2>" + tieu_de + "</h2>" + than + duoi
    )
    return HTMLResponse(khung)


@router.get("/callback")
async def meta_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> HTMLResponse:
    """
    Meta quay về đây sau khi người dùng cấp quyền.

    KHÔNG đòi đăng nhập dashboard: Meta gọi vào và Meta không mang cookie
    phiên của bạn. Chốt an toàn ở bước này là `state` — nó chứng minh lượt
    quay về khớp với lượt bắt đầu do chính quản trị viên khởi động.
    """
    if error:
        return _trang_ket_qua(
            "Bạn đã huỷ cấp quyền",
            "<p>Không có tài khoản nào được nối. Đóng cửa sổ và thử lại nếu cần.</p>",
        )
    nguoi_bam = _KHO_STATE.dung(state)
    if nguoi_bam is None:
        # Không nói rõ vì sao: state sai có thể là hết hạn, có thể là tấn công.
        await db.log_event("oauth.meta.state_khong_hop_le", actor="system")
        return _trang_ket_qua(
            "Phiên kết nối không còn hiệu lực",
            "<p>Hãy đóng cửa sổ, quay lại dashboard và bấm "
            "<b>Kết nối Facebook</b> một lần nữa.</p>",
        )
    if not code:
        return _trang_ket_qua("Thiếu mã cấp quyền", "<p>Hãy thử lại.</p>")

    app_id, app_secret = _app_id_va_secret()
    base = "https://graph.facebook.com/" + GRAPH_VERSION
    try:
        async with httpx.AsyncClient(timeout=25.0) as http:
            # Đổi code lấy token NGƯỜI DÙNG. Bước này chạy phía máy chủ vì nó
            # cần app_secret — thứ không bao giờ được ra trình duyệt.
            r = await http.get(base + "/oauth/access_token", params={
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": _dia_chi_quay_ve(),
                "code": code,
            })
            r.raise_for_status()
            token_nguoi_dung = r.json().get("access_token", "")
            if not token_nguoi_dung:
                raise ValueError("Meta không trả access_token")

            # Danh sách Trang kèm token RIÊNG của từng Trang.
            r2 = await http.get(base + "/me/accounts", params={
                "access_token": token_nguoi_dung,
                # Xin Instagram NGAY trong lời gọi này. Hỏi riêng cho từng Trang là
                # thêm 26 chặng mạng nữa, và người dùng ngồi nhìn màn hình
                # trắng lâu gấp đôi.
                "fields": "id,name,access_token,tasks,instagram_business_account{id,username}",
                "limit": 100,
            })
            r2.raise_for_status()
            danh_sach = doc_trang_tu_me_accounts(r2.json())
    except Exception as exc:  # noqa: BLE001
        await db.log_event(
            "oauth.meta.loi", actor="system",
            error=f"{type(exc).__name__}: {exc}"[:200],
        )
        return _trang_ket_qua(
            "Không lấy được danh sách Trang",
            "<p>Meta từ chối yêu cầu. Kiểm lại META_APP_ID / META_APP_SECRET "
            "và xem mục Nhật ký trên dashboard.</p>",
        )

    if not danh_sach:
        return _trang_ket_qua(
            "Không thấy Trang nào nhắn tin được",
            "<p>Tài khoản Facebook vừa đăng nhập không quản lý Trang nào có "
            "quyền nhắn tin. Kiểm lại bạn có phải quản trị viên của Trang "
            "không.</p>",
        )

    # KHÔNG tạo tài khoản ở đây nữa — hiện danh sách để NGƯỜI DÙNG CHỌN.
    #
    # Bản trước nối thẳng mọi Trang Meta trả về. Một tài khoản quản lý 26
    # Trang thì cả 26 vào hệ thống, phần lớn sai ngành với kho tri thức đang
    # nạp — khách nhắn vào sẽ được tư vấn sai lĩnh vực, và không gì trong hệ
    # thống biết là đang sai.
    #
    # Nối một Trang là NHẬN TRÁCH NHIỆM trả lời khách trên Trang đó. Nó phải
    # là một lựa chọn có ý thức.
    phieu = _kho_chon.tao(nguoi_bam, danh_sach)
    await db.log_event(
        "oauth.meta.hien_chon_trang", actor="system", so_trang=len(danh_sach),
    )
    return _trang_ket_qua("Chọn Trang muốn kết nối",
                          dung_trang_chon(phieu, danh_sach),
                          tu_dong_lam_moi=False)


@router.post("/chon", response_class=HTMLResponse)
async def meta_chon(
    request: Request,
    _nguoi: dict = Depends(bat_buoc_quan_tri),
) -> HTMLResponse:
    """
    Nhận lựa chọn của người dùng rồi mới tạo tài khoản.

    ĐÒI QUYỀN QUẢN TRỊ — KHÁC VỚI CALLBACK
    ---------------------------------------
    Callback được miễn đăng nhập vì Meta gọi vào và không mang cookie của ta.
    Đường này thì ngược lại: chính trình duyệt người dùng gọi, trên origin
    của ta, nên cookie phiên có mặt và phải kiểm.

    Phiếu vẫn là chốt thứ hai: hết hạn hoặc đã dùng thì từ chối.
    """
    form = await request.form()
    phieu = str(form.get("phieu") or "")
    da_chon = {str(x) for x in form.getlist("trang")}

    muc = _kho_chon.dung(phieu)
    if muc is None:
        return _trang_ket_qua(
            "Phiên chọn Trang đã hết hạn",
            "<p>Quay lại dashboard và bấm <b>Kết nối Facebook</b> lần nữa. "
            "Không có Trang nào bị nối trong lần này.</p>",
        )

    nguoi_bam, danh_sach = muc
    chon = [t for t in danh_sach if str(t.get("id")) in da_chon]
    if not chon:
        return _trang_ket_qua(
            "Bạn chưa chọn Trang nào",
            "<p>Không có Trang nào được nối. Bấm <b>Kết nối Facebook</b> lại "
            "nếu muốn chọn.</p>",
        )

    da_noi, chua_dang_ky, da_noi_ig = await _tao_tai_khoan_tu_danh_sach(
        chon, nguoi_bam)
    dong = "".join("<li>" + _thoat(t) + "</li>" for t in da_noi)

    # Nói riêng số Instagram. Gộp vào "đã nối N Trang" thì người dùng không
    # biết Instagram của mình đã vào hay chưa, và sẽ đi khai lại bằng tay.
    khoi_ig = (
        "<p><b>Kèm " + str(len(da_noi_ig)) + " tài khoản Instagram:</b> "
        + _thoat(", ".join(da_noi_ig)) + "</p>"
    ) if da_noi_ig else ""

    # NÓI RA phần chưa xong, không gộp vào con số đẹp.
    #
    # "Đã nối 5 Trang" trong khi 2 Trang chưa đăng ký được webhook là một câu
    # xanh giả: người vận hành đóng tab, yên tâm, rồi vài ngày sau mới phát
    # hiện hai Trang đó chưa từng nhận tin nào.
    canh_bao = (
        "<p><b>" + str(len(chua_dang_ky)) + " Trang chưa nhận được tin:</b> "
        + _thoat(", ".join(chua_dang_ky))
        + "</p><p>Trang đã nối và gửi tin đi được, nhưng chưa đăng ký vào "
        "webhook nên tin khách nhắn vào sẽ không tới. Thường là do quyền "
        "<code>pages_manage_metadata</code> chưa được cấp. Vào mục "
        "<b>Kết nối</b> bấm <b>Nhận tin</b> để thử lại.</p>"
    ) if chua_dang_ky else ""

    return _trang_ket_qua(
        "Đã nối " + str(len(da_noi)) + " Trang",
        "<ul>" + dong + "</ul>" + khoi_ig + canh_bao
        + "<p>Quay lại dashboard, mục <b>Kết nối</b> để xem.</p>",
    )


async def _tao_tai_khoan_tu_danh_sach(
    danh_sach: list[dict], nguoi_bam: Any
) -> tuple[list[str], list[str], list[str]]:
    """
    Tạo channel_account cho từng Trang, credential đi thẳng vào vault.

    Token KHÔNG bao giờ hiện trên màn hình và không đi qua tay người dùng —
    đó là toàn bộ điểm của luồng này.

    Trả `(Trang đã nối, chưa đăng ký webhook, Instagram đã nối)`. Hai con số PHẢI tách rời: có token
    là gửi được tin đi, nhưng NHẬN tin còn cần đăng ký Trang vào webhook —
    một bước hoàn toàn khác, và hỏng thì không có dấu hiệu nào.
    """
    from uuid import UUID

    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_service import (
        AccountActor,
        ChannelAccountService,
        CreateAccountCommand,
    )
    from agent.omnichannel.accounts import Channel
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang
    from agent.security.credential_vault import CredentialVault, parse_master_keys

    _app_id, app_secret = _app_id_va_secret()
    repository = PostgresAccountRepository()
    vault = CredentialVault(
        parse_master_keys(settings.credential_master_keys),
        active_version=settings.credential_active_key_version,
    )
    service = ChannelAccountService(repository, vault)

    # Verify token dùng CHUNG cho mọi Trang của cùng một app: Meta chỉ cho
    # khai một callback URL cho mỗi app, nên nhiều verify token là vô nghĩa.
    verify_token = settings.messenger_verify_token or secrets.token_urlsafe(24)

    # NGƯỜI THẬT đã bấm nút, không phải một id bịa.
    #
    # `account_memberships.user_id` có khoá ngoại tới `nguoi_dung`. Dùng
    # UUID(int=0) thì MỌI lượt tạo tài khoản chết vì ForeignKeyViolation, và
    # người dùng chỉ thấy "Đã nối 0 Trang" — đã xảy ra thật với 6 Trang.
    #
    # `role` chứ không phải `is_admin`: `is_admin` là property suy ra từ
    # role. Đặt nhầm thì actor luôn bị coi là không phải quản trị.
    actor = AccountActor(
        user_id=nguoi_bam if isinstance(nguoi_bam, UUID) else UUID(str(nguoi_bam)),
        role="quan_tri",
    )

    ra: list[str] = []
    chua_dang_ky: list[str] = []
    da_noi_ig: list[str] = []
    for trang in danh_sach:
        try:
            await service.create_account(
                CreateAccountCommand(
                    channel=Channel.FACEBOOK,
                    display_name=trang["name"],
                    external_account_id=trang["id"],
                    capabilities={"send_text": True, "receive_message": True},
                    metadata={"nguon": "oauth"},
                    credentials={
                        "access_token": trang["access_token"],
                        "app_secret": app_secret,
                        "verify_token": verify_token,
                    },
                ),
                actor=actor,
            )
            ra.append(trang["name"])

            # Instagram Business của chính Trang này — nối luôn, không bắt
            # người dùng làm lại từ đầu.
            #
            # Trên Meta, một tài khoản Instagram Business luôn gắn với một
            # Trang, và nhận tin qua CHÍNH Page access token đó. Bắt người
            # dùng đi tìm "token riêng của Instagram" là bắt họ tìm thứ không
            # tồn tại.
            #
            # Một Instagram lỗi không được chặn Trang tiếp theo: nó nằm trong
            # `try` riêng, không dùng chung với Trang.
            if trang.get("instagram_id"):
                try:
                    ten_ig = (trang.get("instagram_username")
                              or trang["name"]) + " (Instagram)"
                    await service.create_account(
                        CreateAccountCommand(
                            channel=Channel.INSTAGRAM,
                            display_name=ten_ig,
                            external_account_id=trang["instagram_id"],
                            capabilities={"send_text": True,
                                          "receive_message": True},
                            metadata={"nguon": "oauth", "trang_lien_ket": trang["id"]},
                            credentials={
                                "access_token": trang["access_token"],
                                "app_secret": app_secret,
                                "verify_token": verify_token,
                            },
                        ),
                        actor=actor,
                    )
                    da_noi_ig.append(ten_ig)
                except Exception as exc:  # noqa: BLE001
                    await db.log_event(
                        "oauth.meta.tao_instagram_loi", actor="system",
                        trang=str(trang.get("name", ""))[:80],
                        error=f"{type(exc).__name__}: {exc}"[:200],
                    )

            # Có tài khoản CHƯA phải là nhận được tin. Trang còn phải được
            # đăng ký vào webhook của app. Thiếu bước này thì mọi dấu hiệu
            # đều nói đã xong, chỉ tin khách là không tới.
            ok, ly_do = await dang_ky_webhook_trang(
                page_id=str(trang["id"]),
                page_token=str(trang["access_token"]),
            )
            if not ok:
                chua_dang_ky.append(trang["name"])
                await db.log_event(
                    "oauth.meta.dang_ky_webhook_loi", actor="system",
                    trang=str(trang.get("name", ""))[:80], error=ly_do,
                )
        except Exception as exc:  # noqa: BLE001 — một Trang lỗi không chặn Trang khác
            await db.log_event(
                "oauth.meta.tao_tai_khoan_loi", actor="system",
                trang=str(trang.get("name", ""))[:80],
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
    return ra, chua_dang_ky, da_noi_ig
