#!/usr/bin/env bash
# Cài máy chủ CSKH trên một VPS Ubuntu 24.04 MỚI — một lệnh, chạy lại được.
#
#   git clone <repo> /srv/cskh && cd /srv/cskh
#   sudo bash trien_khai/cai_vps.sh --email-tls ban@vi-du.vn --erp erp.vi-du.vn
#
# Làm gì (mỗi bước bỏ qua nếu đã làm — chạy lại không hại gì):
#   1. múi giờ Asia/Ho_Chi_Minh, cập nhật bảo mật tự động, fail2ban cho SSH
#   2. swap 4 GB khi RAM < 8 GB (ERPNext + app cùng máy dễ hết RAM lúc dựng)
#   3. tường lửa: chỉ SSH, 80, 443
#   4. Docker Engine (kho chính thức của Docker) + giới hạn kích thước log
#   5. dựng image app + sidecar từ mã nguồn này
#   6. lớp nền (Postgres + Caddy); ERPNext nếu có --erp
#   7. cron: người canh 5 phút, sao lưu 2 giờ sáng, thử phục hồi Chủ nhật,
#      dọn bản sao lưu cũ hơn 14 ngày
#
# KHÔNG làm: trỏ DNS, nhập cửa hàng (bước sau, xem docs/len-vps.md).
set -euo pipefail

EMAIL_TLS=""
ERP_TEN_MIEN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --email-tls) EMAIL_TLS="$2"; shift 2 ;;
    --erp) ERP_TEN_MIEN="$2"; shift 2 ;;
    *) echo "Tham số lạ: $1"; exit 2 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Chạy bằng root: sudo bash $0 ..."; exit 1; }
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || { echo "Script viết cho Ubuntu 24.04 (máy này: ${PRETTY_NAME:-?})"; exit 1; }
GOC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$GOC"
buoc() { printf '\n=== %s\n' "$*"; }

buoc "1. Hệ thống cơ bản"
timedatectl set-timezone Asia/Ho_Chi_Minh || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
# python3-cryptography: mặt phẳng điều khiển chạy bằng python3 của máy và
# giải mã gói chuyển nhà (AES-GCM) — thiếu gói này thì `cua_hang nhap` nổ.
apt-get install -y -q ca-certificates curl git gnupg ufw fail2ban unattended-upgrades \
  python3 python3-cryptography cron logrotate
dpkg-reconfigure -f noninteractive unattended-upgrades || true
systemctl enable --now fail2ban cron

buoc "2. Swap"
RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$RAM_MB" -lt 8000 ] && ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "đã thêm swap 4 GB (RAM ${RAM_MB} MB)"
else
  echo "bỏ qua (RAM ${RAM_MB} MB hoặc đã có swap)"
fi

buoc "3. Tường lửa"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status | head -8
# Ghi chú: Docker tự mở cổng nó publish, vượt qua ufw. Vì thế mọi compose
# ở đây chỉ Caddy publish cổng (80/443) — Postgres, app, ERPNext, sidecar
# đều chỉ nghe trong mạng Docker (tests/test_trien_khai_cong.py canh).

buoc "4. Docker"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Log container không giới hạn là cách đĩa VPS đầy dần rồi Postgres ngừng
# ghi — hỏng im lặng, vài tháng sau.
if [ ! -f /etc/docker/daemon.json ]; then
  printf '{\n  "log-driver": "json-file",\n  "log-opts": {"max-size": "20m", "max-file": "5"}\n}\n' \
    > /etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker
docker --version

buoc "5. Dựng image"
docker build -t cskh-app:latest .
docker build -t cskh-sidecar:latest connectors/zalo-personal-sidecar

buoc "6. Lớp nền"
python3 -m scripts.cua_hang khoi_tao --email-tls "$EMAIL_TLS"
docker compose -f trien_khai/docker-compose.nen.yml --env-file trien_khai/.env.nen up -d
if [ -n "$ERP_TEN_MIEN" ]; then
  python3 -m scripts.cua_hang erp khoi_tao --ten-mien "$ERP_TEN_MIEN"
  python3 -m scripts.cua_hang erp chay
fi

buoc "7. Lịch tự động"
cat > /etc/cron.d/cskh <<CRON
# Sinh bởi trien_khai/cai_vps.sh — người canh, sao lưu, thử phục hồi.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/5 * * * * root cd $GOC && python3 -m scripts.cua_hang kiem --sua >> /var/log/cskh-canh.log 2>&1
0 2 * * *   root cd $GOC && python3 -m scripts.cua_hang sao_luu --tat-ca >> /var/log/cskh-sao-luu.log 2>&1
CRON
if [ -n "$ERP_TEN_MIEN" ]; then
  echo "20 2 * * *  root cd $GOC && python3 -m scripts.cua_hang erp sao_luu >> /var/log/cskh-sao-luu.log 2>&1" >> /etc/cron.d/cskh
fi
cat >> /etc/cron.d/cskh <<CRON
0 4 * * 0   root cd $GOC && python3 -m scripts.cua_hang thu_phuc_hoi --tat-ca >> /var/log/cskh-sao-luu.log 2>&1
30 4 * * *  root find $GOC/trien_khai/sao_luu $GOC/trien_khai/erp/sao_luu -mindepth 1 -mtime +14 -delete 2>/dev/null; true
CRON
chmod 0644 /etc/cron.d/cskh
cat > /etc/logrotate.d/cskh <<'ROT'
/var/log/cskh-*.log {
  weekly
  rotate 8
  compress
  missingok
  notifempty
}
ROT

buoc "XONG"
IP=$(curl -fsS -4 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
cat <<HET
Máy chủ đã sẵn sàng nhận cửa hàng. Việc tiếp theo (chi tiết: docs/len-vps.md):

  1. Trỏ bản ghi A của tên miền cửa hàng${ERP_TEN_MIEN:+ và $ERP_TEN_MIEN} về: $IP
  2. Chép gói chuyển nhà + tệp mật khẩu + khoá GCP lên máy này (scp, HAI lần riêng)
  3. python3 -m scripts.cua_hang nhap <ma> --ten "<Tên>" --ten-mien <tên miền> \\
       --goi <gói.cskh> --mat-khau-tep <tệp> --gcp-khoa <khoá.json>
  4. Khai lại webhook ở Meta và Zalo OA theo tên miền mới
  5. docker exec cskh-<ma>-app python -m scripts.san_sang

Bản sao lưu nằm ở $GOC/trien_khai/sao_luu — CHÉP RA NGOÀI máy chủ.
Webhook báo động của người vận hành: điền CANH_GAC_WEBHOOK trong trien_khai/.env.nen
HET
