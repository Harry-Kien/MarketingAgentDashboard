-- Nhiều hồ sơ agent, thêm bằng CẤU HÌNH chứ không bằng mã.
--
-- MỘT HỒ SƠ AGENT LÀ GÌ
-- ----------------------
-- Một tên, một đoạn hướng dẫn thêm, và hai ngưỡng vận hành. Gán cho một
-- tài khoản kênh thì kênh ấy trả lời theo hồ sơ ấy.
--
-- Ví dụ thật: "Bán hàng Zalo" nói ngắn, chốt đơn nhanh; "Chăm sóc sau bán"
-- kiên nhẫn hơn, ngưỡng tự tin cao hơn nên chuyển người sớm hơn.
--
-- RÀNG BUỘC QUAN TRỌNG NHẤT: CẤU HÌNH CHỈ ĐƯỢC SIẾT, KHÔNG ĐƯỢC NỚI
-- -------------------------------------------------------------------
-- `CLAUDE.md` viết: ràng buộc nằm trong MÃ, không nằm trong prompt. Sáu lớp
-- lưới trong `agent/core/agent.py` canh luật quảng cáo mỹ phẩm và ranh giới
-- tư vấn y tế — những thứ không được phép sai.
--
-- Nếu hồ sơ agent hạ được ngưỡng tự tin, hoặc nâng được trần chi phí, hoặc
-- thay được `SYSTEM`, thì một ô nhập trên dashboard vừa trở thành đường đi
-- vòng qua sáu lớp lưới ấy. Người điền ô đó không hề biết mình đang làm vậy.
--
-- Nên:
--   `nguong_tu_tin`  chỉ được CAO HƠN ngưỡng toàn cục  (chuyển người SỚM hơn)
--   `tran_chi_phi`   chỉ được THẤP HƠN trần toàn cục   (dừng SỚM hơn)
--   `huong_dan`      chỉ THÊM vào khối biến động, không thay `SYSTEM`
--
-- Hai `CHECK` dưới đây canh dấu; phần so với ngưỡng toàn cục canh ở mã
-- (`agent/core/agent_ho_so.py`) vì ngưỡng toàn cục đổi được lúc chạy.

CREATE TABLE IF NOT EXISTS agent_ho_so (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ten           TEXT UNIQUE NOT NULL CHECK (length(ten) BETWEEN 1 AND 80),
    mo_ta         TEXT NOT NULL DEFAULT '',

    -- Hướng dẫn THÊM, đi vào khối biến động sau ngữ cảnh RAG — cùng đường
    -- với hướng dẫn của gói kỹ năng. KHÔNG thay `agent/prompts/system.md`:
    -- thay được nghĩa là gỡ được mọi câu cấm trong đó.
    huong_dan     TEXT NOT NULL DEFAULT '' CHECK (length(huong_dan) <= 4000),

    -- NULL = dùng ngưỡng toàn cục. Có giá trị thì mã sẽ lấy giá trị NGHIÊM
    -- KHẮC HƠN giữa hai bên, không phải giá trị ở đây.
    nguong_tu_tin NUMERIC(4,3) CHECK (nguong_tu_tin BETWEEN 0 AND 1),
    tran_chi_phi  NUMERIC(8,4) CHECK (tran_chi_phi > 0),

    bat           BOOLEAN NOT NULL DEFAULT true,
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Kênh nào dùng hồ sơ nào. NULL = dùng hành vi mặc định như trước bản này.
--
-- ON DELETE SET NULL: xoá một hồ sơ không được làm kênh ngừng trả lời. Kênh
-- rơi về mặc định, và mặc định luôn là hành vi đã chạy từ trước.
ALTER TABLE channel_accounts
    ADD COLUMN IF NOT EXISTS agent_ho_so_id UUID
    REFERENCES agent_ho_so(id) ON DELETE SET NULL;
