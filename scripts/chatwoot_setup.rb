# Dựng sẵn Chatwoot cho Marketing Agent — chạy trong container:
#
#   docker compose -f docker-compose.chatwoot.yml exec -T rails \
#     bundle exec rails runner - < scripts/chatwoot_setup.rb
#
# Idempotent: chạy lại nhiều lần không tạo trùng.
#
# Việc nó làm:
#   1. Tạo tổ chức "Aurora Skin"
#   2. Tạo tài khoản quản trị (mật khẩu đọc từ biến môi trường)
#   3. Tạo hộp thư kênh API — nhận tin ngay, KHÔNG cần Meta duyệt gì
#   4. Đăng ký webhook trỏ về Marketing Agent
#
# Vì sao hộp thư kênh API: Facebook/Instagram trong Chatwoot vẫn cần App
# Review như mọi đường khác. Kênh API nhận tin được ngay, nên toàn bộ luồng
# đa nền tảng chạy và demo được từ hôm nay; khi Meta duyệt xong thì chỉ
# thêm hộp thư mới, adapter không đổi.

require 'securerandom'

EMAIL = ENV.fetch('CW_ADMIN_EMAIL')
PASSWORD = ENV.fetch('CW_ADMIN_PASSWORD')
WEBHOOK = ENV.fetch('CW_WEBHOOK_URL')

account = Account.find_by(name: 'Aurora Skin') || Account.create!(name: 'Aurora Skin')

user = User.find_by(email: EMAIL)
if user.nil?
  user = User.new(name: 'Quan tri', email: EMAIL,
                  password: PASSWORD, password_confirmation: PASSWORD)
  user.skip_confirmation! if user.respond_to?(:skip_confirmation!)
  user.save!
end

unless AccountUser.exists?(account_id: account.id, user_id: user.id)
  AccountUser.create!(account_id: account.id, user_id: user.id,
                      role: :administrator)
end

inbox = account.inboxes.find_by(name: 'Aurora Skin - API')
if inbox.nil?
  channel = Channel::Api.create!(account: account, webhook_url: '')
  inbox = Inbox.create!(account: account, channel: channel,
                        name: 'Aurora Skin - API')
end
InboxMember.find_or_create_by!(inbox_id: inbox.id, user_id: user.id)

hook = account.webhooks.find_by(url: WEBHOOK)
if hook.nil?
  account.webhooks.create!(url: WEBHOOK, webhook_type: :account_type,
                           subscriptions: %w[message_created])
end

token = user.access_token&.token || AccessToken.find_by(owner: user)&.token

puts '=== CHATWOOT SAN SANG ==='
puts "ACCOUNT_ID=#{account.id}"
puts "INBOX_ID=#{inbox.id}"
puts "INBOX_IDENTIFIER=#{inbox.channel.try(:identifier)}"
puts "API_TOKEN=#{token}"
puts "WEBHOOK=#{WEBHOOK}"
