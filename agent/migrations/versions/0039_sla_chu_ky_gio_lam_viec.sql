-- SLA theo CHU KỲ và theo GIỜ LÀM VIỆC (DEV-01, DEV-06 — rà soát 12.11.2026).
--
-- LỖI 1 — MỞ LẠI VẪN DÙNG HẠN CŨ
-- `prevent_sla_deadline_reset` (0005) không bao giờ cho đổi hạn đã đặt. Đúng
-- trong MỘT lượt phục vụ: đổi ưu tiên hay gán lại không được làm hạn trôi đi.
-- Nhưng `giai_quyet.mo_lai_neu_da_giai_quyet` tính hạn MỚI khi khách nhắn
-- lại sau khi đã giải quyết — và trigger lặng lẽ đè về hạn CŨ, đã qua từ
-- lâu. Hội thoại vừa mở lại đã "trễ SLA" ngay giây đầu.
--
-- LỖI 2 — CHU KỲ THỨ HAI KHÔNG GHI ĐƯỢC LỊCH SỬ
-- `sla_events` có UNIQUE (conversation_id, kind): mỗi loại sự kiện một lần
-- trên MỘT hội thoại. Lượt phục vụ thứ hai không ghi được "started", "đạt"
-- hay "trễ" — ON CONFLICT DO NOTHING nuốt im.
--
-- CÁCH SỬA: mỗi hội thoại có số chu kỳ SLA. Mở lại = chu kỳ + 1. Trigger chỉ
-- cho đặt hạn mới khi chu kỳ TĂNG; trong cùng chu kỳ vẫn chặn như cũ. Sự
-- kiện mang số chu kỳ, nên lịch sử chu kỳ cũ giữ nguyên.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS sla_chu_ky INT NOT NULL DEFAULT 1;
ALTER TABLE sla_events ADD COLUMN IF NOT EXISTS chu_ky INT NOT NULL DEFAULT 1;
ALTER TABLE sla_events DROP CONSTRAINT IF EXISTS sla_events_conversation_id_kind_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sla_events_chu_ky
    ON sla_events (conversation_id, chu_ky, kind);

CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
BEGIN
    -- Chu kỳ mới (mở lại hội thoại): hạn mới là đúng, cho qua.
    IF NEW.sla_chu_ky > OLD.sla_chu_ky THEN
        RETURN NEW;
    END IF;
    IF OLD.first_response_due_at IS NOT NULL
       AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
        NEW.first_response_due_at := OLD.first_response_due_at;
    END IF;
    IF OLD.resolution_due_at IS NOT NULL
       AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
        NEW.resolution_due_at := OLD.resolution_due_at;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- HẠN SLA THEO GIỜ LÀM VIỆC (DEV-06)
-- Trước đây hạn = bây giờ + N phút, tính liên tục 24/7: khách nhắn 20:55,
-- hạn phản hồi 15 phút rơi vào 21:10 — sau giờ đóng cửa — và sáng hôm sau
-- mọi hội thoại đêm qua đều "trễ". Báo cáo trễ SLA của từng nhân viên sai
-- theo cách không ai sửa được.
--
-- Đồng hồ chỉ chạy trong [gio_mo, gio_dong) giờ Việt Nam (UTC+7 cố định —
-- xem agent/core/gio_lam_viec.py), MỌI ngày trong tuần (cửa hàng mở cả
-- tuần). Ngoài giờ thì dừng, mở cửa hôm sau chạy tiếp phần còn lại.
-- gio_mo >= gio_dong (hoặc thiếu) = trực 24/7: hỏng theo hướng phục vụ
-- khách, cùng quy ước với dang_trong_gio().
CREATE OR REPLACE FUNCTION sla_han(bat_dau TIMESTAMPTZ, phut INTEGER,
                                   gio_mo INTEGER, gio_dong INTEGER)
RETURNS TIMESTAMPTZ LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    t      TIMESTAMP;            -- giờ Việt Nam, không múi
    con    INTERVAL;
    mo     TIMESTAMP;
    dong   TIMESTAMP;
    du     INTERVAL;
BEGIN
    IF bat_dau IS NULL OR phut IS NULL THEN
        RETURN NULL;
    END IF;
    con := make_interval(mins => GREATEST(phut, 0));
    IF gio_mo IS NULL OR gio_dong IS NULL OR gio_mo < 0 OR gio_dong > 24
       OR gio_mo >= gio_dong THEN
        RETURN bat_dau + con;
    END IF;
    t := (bat_dau AT TIME ZONE 'UTC') + INTERVAL '7 hours';
    LOOP
        mo   := date_trunc('day', t) + make_interval(hours => gio_mo);
        dong := date_trunc('day', t) + make_interval(hours => gio_dong);
        IF t < mo THEN
            t := mo;
        END IF;
        IF t >= dong THEN
            t := date_trunc('day', t) + INTERVAL '1 day' + make_interval(hours => gio_mo);
            CONTINUE;
        END IF;
        du := dong - t;
        IF con <= du THEN
            t := t + con;
            EXIT;
        END IF;
        con := con - du;
        t := date_trunc('day', t) + INTERVAL '1 day' + make_interval(hours => gio_mo);
    END LOOP;
    RETURN (t - INTERVAL '7 hours') AT TIME ZONE 'UTC';
END
$$;

-- Giờ mở/đóng của MỘT chính sách SLA: `business_hours` {"bat_dau": 8,
-- "ket_thuc": 21} ghi đè giờ chung. Ô này là JSON tự do do người quản trị
-- nhập — một giá trị gõ sai không được làm hỏng việc TẠO HỘI THOẠI, nên
-- đọc hỏng thì lui về giờ chung.
CREATE OR REPLACE FUNCTION sla_gio(gio JSONB, khoa TEXT, mac_dinh INTEGER)
RETURNS INTEGER LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN coalesce((gio ->> khoa)::INTEGER, mac_dinh);
EXCEPTION WHEN others THEN
    RETURN mac_dinh;
END
$$;
