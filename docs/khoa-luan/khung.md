# Khung khóa luận — dàn ý và bản đồ bằng chứng

> Tệp này **không phải** văn khóa luận. Nó là dàn ý cùng chỗ trỏ tới bằng
> chứng trong repo cho từng mục, để người viết không phải đi tìm và không
> viết điều mã không chứng minh được. Văn khóa luận do tác giả viết.
>
> Quy ước: **[Có]** = bằng chứng đã có trong repo · **[Đo]** = cần chạy phép
> đo (tốn tiền API, hỏi chủ dự án) · **[Viết]** = chỉ tác giả viết được.

---

## Mở đầu

| Mục | Nội dung cần có | Căn cứ |
|---|---|---|
| Bối cảnh | Shop mỹ phẩm VN bán qua Zalo/Facebook; nhân viên trả lời tay; luật quảng cáo mỹ phẩm và ranh giới tư vấn y tế | [Viết]; `docs/co-so-ly-thuyet.md` mục pháp lý |
| Bài toán | Tự động hoá CSKH đa kênh bằng LLM mà KHÔNG vi phạm luật quảng cáo và không tư vấn y tế ngoài thẩm quyền | [Viết] |
| **Câu hỏi nghiên cứu** | **CH1.** Ràng buộc hiện thực trong mã (lớp lưới tất định) giảm tỉ lệ bỏ sót chuyển người bao nhiêu so với chỉ dựa vào prompt? **CH2.** Mỗi lớp lưới có bắt một kiểu trượt riêng mà lớp khác không bắt — tức xếp chồng có cần thiết? **CH3.** Hệ thống có giữ được tỉ lệ dùng từ cấm quảng cáo bằng 0 mà không chuyển người thừa quá mức? | [Đo] `docs/thuc-nghiem.md` mục 2.2, 2.4 |
| Mục tiêu, phạm vi | Một cửa hàng, tiếng Việt, mỹ phẩm; đa kênh; không thay bác sĩ/dược sĩ | `README.md`, `docs/dua-vao-doanh-nghiep.md` |
| **Đóng góp** | (1) Kiến trúc "ràng buộc nằm trong mã" với các lớp lưới tất định đo được bằng ablation; (2) phương pháp tài liệu sinh từ dữ liệu, có test canh tài liệu cũ; (3) hệ thống CSKH đa kênh vận hành được (RBAC hỏng-đóng, outbox bền vững, Customer 360 hoàn tác được) | [Có] `agent/core/agent.py::LOP_LUOI`, `scripts/sinh_*.py`, `agent/core/quyen.py` |

## Chương 1 — Tổng quan và công trình liên quan

| Mục | Đọc / trích | Ghi chú |
|---|---|---|
| RAG | Lewis et al. 2020 [1] | đã trích trong `co-so-ly-thuyet.md` |
| Dùng công cụ | Schick et al. 2023 (Toolformer) [3]; Yao et al. 2023, "ReAct", ICLR 2023, arXiv:2210.03629 | ReAct chưa có trong danh mục — thêm khi viết |
| Guardrails | Rebedea et al. 2023, "NeMo Guardrails", EMNLP 2023 Demos, arXiv:2310.10501; Inan et al. 2023, "Llama Guard", arXiv:2312.06674 | **So sánh trọng tâm**: guardrail của họ chạy bằng model/DSL; lớp lưới ở đây là mã tất định đặc thù miền — nêu ưu/nhược |
| Prompt injection | OWASP Top 10 LLM [5]; Greshake et al. 2023, "Not what you've signed up for", AISec '23, arXiv:2302.12173 | lưới `injection` |
| Đánh giá LLM | Es et al. 2024, "RAGAS", EACL 2024 Demos, arXiv:2309.15217; Zheng et al. 2023, "Judging LLM-as-a-Judge", NeurIPS 2023 D&B, arXiv:2306.05685 | giải thích vì sao bộ đo ở đây chấm bằng luật + từ khoá, và giới hạn của nó |
| Sản phẩm CSKH | Pancake, Haravan HaraSocial, Sapo, Subiz; Chatwoot, Zendesk, Intercom | [Viết] bảng so sánh — xem `docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md` |
| Pháp lý | Luật Quảng cáo [11]; Luật BVDLCN 91/2025 [8] | |

## Chương 2 — Cơ sở lý thuyết

→ `docs/co-so-ly-thuyet.md` (đã có). Khi chuyển sang văn khóa luận: giữ mục
6 (các lớp lưới) làm trung tâm, rút gọn phần hướng dẫn vận hành.

## Chương 3 — Phân tích và thiết kế

| Mục | Căn cứ |
|---|---|
| Kiến trúc tổng thể, sơ đồ CSDL | `docs/kien-truc.md` (sinh từ mã) |
| Luồng một tin nhắn: webhook → inbox → agent → outbox | `agent/omnichannel/xu_ly_tin_vao.py::handle_inbound`, `agent/omnichannel/` |
| Phân quyền hỏng-đóng | `agent/core/quyen.py`, `kiem_moi_route_co_quyen` |
| Bảo mật | AES-256-GCM `agent/security/credential_vault.py`; scrypt + phiên băm `agent/core/xac_thuc.py`; HMAC webhook |

## Chương 4 — Hiện thực

| Mục | Căn cứ |
|---|---|
| Agent và sáu lớp lưới | `agent/core/agent.py` |
| Kênh | `agent/channels/`, `connectors/zalo-personal-sidecar` |
| Dashboard | `dashboard/` |
| Kiểm thử tất định, CI | `tests/`, `.github/workflows/kiem-thu.yml` (Postgres thật, clone sạch, độ phủ, sidecar) |
| Nghiệm thu chức năng | `docs/nghiem-thu.md` (sinh từ lần chạy thật) |

## Chương 5 — Thực nghiệm và đánh giá

| Mục | Trạng thái |
|---|---|
| Phương pháp, bộ câu vàng, tiêu chí chấm | [Có] `docs/thuc-nghiem.md` mục 2.1 |
| Lặp có kiểm soát (≥5 lần, cùng commit) | [Đo] `python -m scripts.eval --lap 5` |
| Đối chứng chỉ-prompt | [Đo] `python -m scripts.eval --chi-prompt --lap 5` |
| Ablation từng lớp | [Đo] `python -m scripts.eval --tat-luoi <ma> --lap 3` cho từng lớp |
| Bộ nhiều lượt | [Đo] `python -m scripts.eval_nhieu_luot` |
| Thống kê | [Có] Wilson 95%, TB ± ĐLC — `scripts/sinh_thuc_nghiem.py` |
| Số liệu vận hành thật | [Đo] cần thời gian chạy thí điểm: số tin, tỉ lệ chuyển người, độ trễ p50/p95, chi phí/hội thoại |
| Độ khách quan bộ vàng | [Viết] nhờ 1–2 người trong nghề gán nhãn độc lập một mẫu, báo hệ số kappa |

## Chương 6 — Kết luận, hạn chế, hướng phát triển

| Mục | Căn cứ |
|---|---|
| Trả lời CH1–CH3 | từ Chương 5 |
| Hạn chế | `docs/thuc-nghiem.md` mục 5 (không tất định, chấm từ khoá, dữ liệu hư cấu, một model) + Zalo cá nhân dùng API không chính thức |
| Hướng phát triển | lộ trình SaaS: đa thuê bao, gói cước, tuân thủ Luật BVDLCN 91/2025 — `docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md` |

## Phụ lục

- Bảng nghiệm thu chức năng (`docs/nghiem-thu.md`)
- Kết quả eval đã ẩn danh (từ `data/eval/ket-qua-*.json`, bỏ giá thật nếu có)
- Danh mục quyền (`agent/core/quyen.py`)
