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

account_name = ENV.fetch('CW_ACCOUNT_NAME', 'Aurora Skin')
inbox_name = ENV.fetch('CW_WEB_INBOX_NAME', "#{account_name} - Website")
widget_color = ENV.fetch('CW_WIDGET_COLOR', '#0068FF')
welcome_title = ENV.fetch('CW_WELCOME_TITLE', "#{account_name} xin chào")
welcome_tagline = ENV.fetch('CW_WELCOME_TAGLINE', 'Bạn cần hỗ trợ gì ạ?')

account = Account.find_by(name: account_name) or abort("Chưa có tổ chức #{account_name}")
user = User.find_by(email: ENV.fetch('CW_ADMIN_EMAIL'))

inbox = account.inboxes.find_by(name: inbox_name)
if inbox.nil?
  channel = Channel::WebWidget.create!(
    account: account,
    website_url: ENV.fetch('CW_WEBSITE_URL', 'http://localhost:8000'),
    widget_color: widget_color,
    welcome_title: welcome_title,
    welcome_tagline: welcome_tagline,
    reply_time: 'in_a_few_minutes'
  )
  inbox = Inbox.create!(account: account, channel: channel,
                        name: inbox_name)
end
InboxMember.find_or_create_by!(inbox_id: inbox.id, user_id: user.id) if user

puts '=== KENH WEBSITE SAN SANG ==='
puts "INBOX_ID=#{inbox.id}"
puts "WEBSITE_TOKEN=#{inbox.channel.website_token}"
puts "SCRIPT_NHUNG=#{ENV.fetch('CW_BASE_URL', 'http://localhost:3200')}/packs/js/sdk.js"
