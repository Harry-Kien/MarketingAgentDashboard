/* UX-LS-02/03: independent server-side history pages; no live role lookup is
 * required to render a deleted role's immutable event. */
function lsQuyenDoi(d) {
  const c = d.chi_tiet || {};
  const nv = d.loai === 'nguoi_dung.vai_tro';
  const truoc = c.truoc?.quyen || [];
  const sau = c.sau?.quyen || [];
  return {
    them: (nv ? c.quyen_them : c.them) || sau.filter(q => !truoc.includes(q)),
    bot: (nv ? c.quyen_bot : c.bot) || truoc.filter(q => !sau.includes(q)),
    truoc, sau,
  };
}
function lsTenDoiTuong(d) {
  const c = d.chi_tiet || {};
  return c.ten || c.ten_dang_nhap || c.ten_moi || c.sau?.ten || c.truoc?.ten || d.ref_id || 'Đối tượng';
}
function lsMoQuyen(d) {
  const q = lsQuyenDoi(d), c = d.chi_tiet || {};
  const trigger = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.className = 'ls-doi-quyen';
  dialog.setAttribute('aria-labelledby', 'lsQuyenTitle');
  const ds = a => a.length ? `<ul>${a.map(x => `<li>${esc(nsvNhanQuyen(x))}</li>`).join('')}</ul>` : '<p class="hint">Không có</p>';
  dialog.innerHTML = `<div class="ls-doi-quyen__dau">
      <h2 id="lsQuyenTitle">Chi tiết thay đổi quyền</h2>
      <button type="button" class="btn btn--sm btn--ghost ls-doi-quyen__x" data-ls-close aria-label="Đóng">✕</button>
    </div>
    <p class="ls-doi-quyen__meta">${esc(lsTenDoiTuong(d))} · ${esc(d.nguoi_lam || 'Hệ thống')} · ${esc(nsvNgay(d.luc))}</p>
    <div class="ls-doi-quyen__than">
      <div class="ls-hai-cot"><section><h3>Trước thay đổi</h3><p>${esc(c.truoc?.ten || lsTenDoiTuong(d))}</p>${Array.isArray(c.truoc) ? ds(c.truoc) : ds(q.truoc)}</section>
      <section><h3>Sau thay đổi</h3><p>${d.loai === 'vai_tro.xoa' ? 'Vai trò đã bị xóa' : esc(c.sau?.ten || lsTenDoiTuong(d))}</p>${Array.isArray(c.sau) ? ds(c.sau) : ds(q.sau)}</section></div>
      <div class="ls-hai-cot"><section><h3>Quyền được cấp (${q.them.length})</h3>${ds(q.them)}</section>
      <section><h3>Quyền bị thu hồi (${q.bot.length})</h3>${ds(q.bot)}</section></div>
    </div>
    <form method="dialog" class="ls-doi-quyen__chan"><button class="btn btn--sm btn--primary">Đóng</button></form>`;
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog || e.target.closest('[data-ls-close]')) dialog.close();
  });
  dialog.addEventListener('close', () => { dialog.remove(); trigger?.focus(); }, {once:true});
  document.body.append(dialog);
  dialog.showModal();
}
async function nsvLichSuHaiCot(el) {
  if (!coQuyen('nguoi_dung.doc')) {
    el.innerHTML = '<p class="empty">Bạn không có quyền xem lịch sử nhân sự.</p>'; return;
  }
  if (!nsv.nhom.length) {
    try { nsv.nhom = (await api('/quyen')).nhom_hien_thi || []; }
    catch (e) { toast(`Không tải được nhãn quyền: ${e.message}`, true); }
  }
  const bo = Object.fromEntries(['nguoi_dung','vai_tro'].map(k => [k,{ cursors:[], next:null, seq:0, rows:[] }]));
  let activeMobTab = 'nguoi_dung';
  el.innerHTML = `<div class="ls-hai-cot" data-ls-tab="${activeMobTab}">
    <div class="tabs ls-subtabs" role="tablist" aria-label="Nhóm lịch sử nhân sự">
      <button type="button" class="tab is-on" role="tab" data-ls-subtab="nguoi_dung" aria-selected="true">Nhân viên</button>
      <button type="button" class="tab" role="tab" data-ls-subtab="vai_tro" aria-selected="false">Vai trò &amp; Quyền</button>
    </div>
    ${Object.keys(bo).map(k => `<section class="panel" data-ls-cot="${k}" data-ls-nhom="${k}">
    <h2 class="panel__head">${k === 'nguoi_dung' ? 'Lịch sử nhân viên' : 'Lịch sử vai trò và quyền hạn'}</h2>
    <form class="nsv-loc" data-ls-loc="${k}"><label class="field"><span>Tìm đối tượng / người thực hiện</span>
    <input type="search" name="q" maxlength="120" placeholder="Nhập tên, kể cả vai trò đã xóa"></label>
    <button class="btn btn--sm btn--ghost">Lọc</button></form>
    <div class="rows ls-cuon" data-ls-rows="${k}" aria-live="polite"></div>
    <nav class="ls-trang" data-ls-pager="${k}" aria-label="Phân trang ${k === 'nguoi_dung' ? 'nhân viên' : 'vai trò'}"></nav>
    </section>`).join('')}</div>`;
  function chonSubtab(tab) {
    activeMobTab = tab === 'vai_tro' ? 'vai_tro' : 'nguoi_dung';
    const grid = el.querySelector('.ls-hai-cot');
    if (grid) grid.dataset.lsTab = activeMobTab;
    el.querySelectorAll('[data-ls-subtab]').forEach(b => {
      const on = b.dataset.lsSubtab === activeMobTab;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }
  async function tai(k) {
    const s = bo[k], seq = ++s.seq;
    const rows = el.querySelector(`[data-ls-rows="${k}"]`), pager = el.querySelector(`[data-ls-pager="${k}"]`);
    const q = new URLSearchParams({loai:k, limit:'20', q:el.querySelector(`[data-ls-loc="${k}"] input`).value.trim()});
    if (s.cursors.length) q.set('truoc',s.cursors.at(-1));
    rows.innerHTML = '<p class="empty">Đang tải…</p>'; pager.innerHTML = '';
    try {
      const d = await api('/nhan-su/lich-su?' + q);
      if (seq !== s.seq) return;
      s.rows = d.lich_su; s.next = d.next_cursor;
      rows.innerHTML = s.rows.length ? s.rows.map(d => {
        const z = lsQuyenDoi(d);
        const flag = z.bot.length || d.loai === 'vai_tro.xoa' || d.loai === 'auth.khoa_nguoi_dung' ? 'assist' : 'auto';
        return `<div class="row"><span class="row__flag row__flag--${flag}"></span><div class="row__main"><b>${esc(d.nhan)} · ${esc(lsTenDoiTuong(d))}</b>
          <span class="row__sub">${esc(d.nguoi_lam || 'Hệ thống')} · ${esc(nsvNgay(d.luc))}</span>
          <span class="row__sub">Cấp ${z.them.length} quyền · Thu hồi ${z.bot.length} quyền</span>
          <div><button type="button" class="btn btn--sm btn--ghost" data-ls-detail="${esc(d.id)}" data-ls-kind="${k}">Xem chi tiết</button></div>
          </div></div>`;
      }).join('') : '<p class="empty">Không có lịch sử phù hợp.</p>';
      pager.innerHTML = `<button class="btn btn--sm btn--ghost" data-ls-prev="${k}" ${s.cursors.length ? '' : 'disabled'}>Trước</button>
        <span>Trang ${s.cursors.length+1}</span><button class="btn btn--sm btn--ghost" data-ls-next="${k}" ${s.next ? '' : 'disabled'}>Sau</button>`;
    } catch(e) {
      if (seq === s.seq) rows.innerHTML = `<p class="empty" role="alert">Không tải được lịch sử: ${esc(e.message)}</p><button class="btn btn--sm btn--ghost" data-ls-retry="${k}">Thử lại</button>`;
    }
  }
  el.addEventListener('submit',e => {
    const f = e.target.closest('[data-ls-loc]'); if (!f) return;
    e.preventDefault(); bo[f.dataset.lsLoc].cursors = []; tai(f.dataset.lsLoc);
  });
  el.addEventListener('click',e => {
    const b = e.target.closest('button'); if (!b || b.disabled) return;
    if (b.dataset.lsSubtab) { chonSubtab(b.dataset.lsSubtab); return; }
    if (b.dataset.lsDetail) { const d = bo[b.dataset.lsKind].rows.find(x => String(x.id) === b.dataset.lsDetail); if (d) lsMoQuyen(d); }
    if (b.dataset.lsNext) { const k=b.dataset.lsNext; if (bo[k].next) { bo[k].cursors.push(bo[k].next); tai(k); } }
    if (b.dataset.lsPrev) { const k=b.dataset.lsPrev; bo[k].cursors.pop(); tai(k); }
    if (b.dataset.lsRetry) tai(b.dataset.lsRetry);
  });
  await Promise.all(Object.keys(bo).map(tai));
}
