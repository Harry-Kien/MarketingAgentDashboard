# Đặt hộp thư ở trạng thái LUÔN TRỰC.
#
# VÌ SAO
# ------
# Chatwoot hiện "We are away at the moment" khi không nhân viên nào đang
# online. Với hộp thư do agent xử lý 24/7 thì câu đó vừa sai vừa có hại:
# khách đọc xong nghĩ không ai trả lời và bỏ đi, trong khi agent trả lời
# trong vài giây.
#
# Hai việc:
#   1. Đặt tài khoản vận hành ở trạng thái online
#   2. Đổi câu chờ thành câu đúng với thực tế
account = Account.find_by(name: 'Aurora Skin') or abort('Chưa có tổ chức')

AccountUser.where(account_id: account.id).find_each do |au|
  au.update!(availability: :online, auto_offline: false)
end

account.inboxes.where(name: 'Aurora Skin - Website').find_each do |inbox|
  ch = inbox.channel
  ch.update!(
    reply_time: 'in_a_few_minutes',
    welcome_title: 'Aurora Skin xin chào',
    welcome_tagline: 'Bạn cần tư vấn về da hay sản phẩm nào ạ?'
  ) if ch.respond_to?(:reply_time)
  inbox.update!(
    working_hours_enabled: false,
    out_of_office_message: nil,
    greeting_enabled: true,
    greeting_message: 'Dạ Aurora Skin đây, mình cần tư vấn gì ạ?'
  )
end

puts '=== DA DAT LUON TRUC ==='
AccountUser.where(account_id: account.id).each do |au|
  puts "  user #{au.user_id}: availability=#{au.availability} auto_offline=#{au.auto_offline}"
end
account.inboxes.each do |i|
  puts "  inbox #{i.id} #{i.name}: working_hours=#{i.working_hours_enabled} greeting=#{i.greeting_enabled}"
end
