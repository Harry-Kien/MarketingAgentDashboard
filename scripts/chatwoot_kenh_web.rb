# Tạo hộp thư "khung chat website" trong Chatwoot.
#
#   docker compose -f docker-compose.chatwoot.yml exec -T rails \
#     bundle exec rails runner - < scripts/chatwoot_kenh_web.rb
#
# VÌ SAO KÊNH NÀY ĐÁNG LÀM TRƯỚC
# ------------------------------
# Facebook, Instagram và WhatsApp trong Chatwoot đều cần Meta duyệt quyền —
# 1 đến 4 tuần, và có thể bị từ chối. Khung chat website thì KHÔNG cần ai
# duyệt: dán một đoạn script vào web là chạy.
#
# Với doanh nghiệp mỹ phẩm, đây cũng là kênh có giá trị nhất trong ba kênh
# đó: khách đang xem sản phẩm trên web chính là lúc họ gần quyết định mua
# nhất.
#
# Idempotent: chạy lại không tạo trùng.

account = Account.find_by(name: 'Aurora Skin') or abort('Chưa có tổ chức Aurora Skin')
user = User.find_by(email: ENV.fetch('CW_ADMIN_EMAIL'))

inbox = account.inboxes.find_by(name: 'Aurora Skin - Website')
if inbox.nil?
  channel = Channel::WebWidget.create!(
    account: account,
    website_url: ENV.fetch('CW_WEBSITE_URL', 'http://localhost:8000'),
    widget_color: '#0068FF',
    welcome_title: 'Aurora Skin xin chào',
    welcome_tagline: 'Bạn cần tư vấn về da hay sản phẩm nào ạ?',
    reply_time: 'in_a_few_minutes'
  )
  inbox = Inbox.create!(account: account, channel: channel,
                        name: 'Aurora Skin - Website')
end
InboxMember.find_or_create_by!(inbox_id: inbox.id, user_id: user.id) if user

puts '=== KENH WEBSITE SAN SANG ==='
puts "INBOX_ID=#{inbox.id}"
puts "WEBSITE_TOKEN=#{inbox.channel.website_token}"
puts "SCRIPT_NHUNG=#{ENV.fetch('CW_BASE_URL', 'http://localhost:3200')}/packs/js/sdk.js"
