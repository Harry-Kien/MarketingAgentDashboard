-- agent/migrations/versions/0016_mcp_may_chu.sql
-- Máy chủ MCP bên ngoài mà agent được phép gọi công cụ.
--
-- VÌ SAO KHÔNG CÓ BẢNG CÔNG CỤ RIÊNG: công cụ của máy chủ ghi vào
-- `ky_nang_cai_dat` với `goi = 'mcp:<ten>'`, để mọi chốt đã có cho plugin
-- có chủ (không xoá lẻ, không ghi đè bằng form, tắt theo chủ, trần 12, số
-- đo) áp dụng nguyên xi. Một bảng riêng là một đường thứ hai vào mô hình
-- không đi qua chốt nào.
--
-- VÌ SAO BÍ MẬT NẰM NGAY TRONG BẢNG: header xác thực mã hoá bằng đúng vault
-- của credential kênh (AES-256-GCM, AAD theo phạm vi `mcp:<ten>`), cùng ba
-- cột nonce/ciphertext/key_version như `cau_hinh_bi_mat`. NULL = không có.

CREATE TABLE IF NOT EXISTS mcp_may_chu (
    ten          TEXT PRIMARY KEY,
    nhan         TEXT NOT NULL,
    dia_chi      TEXT NOT NULL,
    bat          BOOLEAN NOT NULL DEFAULT TRUE,
    key_version  INTEGER,
    nonce        BYTEA,
    ciphertext   BYTEA,
    suc_khoe     JSONB NOT NULL DEFAULT '{}',
    tao_boi      TEXT NOT NULL,
    tao_luc      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc      TIMESTAMPTZ NOT NULL DEFAULT now()
);
