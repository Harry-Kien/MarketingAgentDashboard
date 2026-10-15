# Sidecar Zalo cá nhân — một container cho mỗi cửa hàng, cạnh container app.
#
# Không ghi phiên ra đĩa: app nạp lại phiên từ kho bí mật (AES-GCM) khi
# sidecar khởi động lại, nên container này không cần volume.
FROM node:22-slim

ENV NODE_ENV=production \
    # Trong mạng nội bộ của cửa hàng: app gọi sidecar bằng tên dịch vụ, nên
    # phải nghe trên mọi giao diện CỦA CONTAINER — cổng không mở ra ngoài.
    ZALO_SIDECAR_HOST=0.0.0.0 \
    ZALO_SIDECAR_PORT=3210

WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src

USER node
EXPOSE 3210
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3210/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/server.mjs"]
