# Image của app CSKH — MỘT image cho mọi cửa hàng (mô hình silo: mỗi cửa
# hàng một container từ image này, một CSDL riêng). Xem
# docs/superpowers/plans/2026-10-15-giai-doan-2-nen-saas-silo.md.
#
# Không chạy bằng root: app nhận tệp khách gửi và gọi ffmpeg — một lỗ trong
# đường xử lý tệp mà chạy root là chiếm được cả container.
FROM python:3.12-slim

# ffmpeg cho dựng video; fonts cho phụ đề tiếng Việt; curl cho HEALTHCHECK.
# Gỡ danh sách apt để image nhỏ — mỗi cửa hàng kéo image này một lần.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VAI_TRO_TIEN_TRINH=tat_ca

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY agent ./agent
COPY dashboard ./dashboard
COPY scripts ./scripts
# Dữ liệu đi theo repo (catalog/tri thức mẫu, ảnh sản phẩm mẫu, gói kỹ năng)
# vào /app/data_mac_dinh. /app/data là VOLUME riêng của từng cửa hàng —
# entrypoint chép bản mặc định sang khi còn thiếu, KHÔNG BAO GIỜ ghi đè.
COPY data ./data_mac_dinh
COPY trien_khai/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin cskh \
 && chmod 0755 /usr/local/bin/entrypoint.sh \
 && mkdir -p /app/data \
 && chown -R cskh:cskh /app/data
USER cskh
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# MỖI CỬA HÀNG ĐÚNG MỘT TIẾN TRÌNH (VAI_TRO_TIEN_TRINH=tat_ca, không
# --workers): outbox, lịch đăng bài, sao lưu không chịu được hai bản chạy.
# --proxy-headers: đứng sau Caddy, IP thật của khách nằm trong
# X-Forwarded-For — bộ đếm chống dò mật khẩu theo IP cần nó.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "agent.main:app", "--host", "0.0.0.0", \
     "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
