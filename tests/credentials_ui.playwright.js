/* Browser-tool runner: load this file and call testCredentialsUI(page, source).
 * source is dashboard/src/22-ket-noi-tich-hop.js. No backend/network is used.
 */
async function testCredentialsUI(page, source) {
  await page.setContent('<main id="root"></main>');
  await page.addStyleTag({ content: '[hidden]{display:none!important}' });
  await page.addScriptTag({ content: `
    window.GAN_TAB = {};
    window.esc = s => String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
    window.$$ = (s, root=document) => [...root.querySelectorAll(s)];
    window._oDaSua = o => o.value !== o.defaultValue;
    window.toast = () => {};
    window.requests = [];
    window.api = async (url, opts) => {
      const body = JSON.parse(opts.body);
      requests.push({url, ...body});
      return url.endsWith('/kiem-tra')
        ? {ok:true, chi_tiet:'Mock OK', dung_gia_tri_luu:false}
        : {hong:[], da_luu:Object.keys(body.gia_tri)};
    };
  ` });
  await page.addScriptTag({ content: source });
  await page.evaluate(() => {
    const secret = (khoa, nguon='csdl', da_dat=true) => ({
      khoa, nhan:khoa, bi_mat:true, da_dat, hien:da_dat?'···abcd':'', nguon,
    });
    const fields = [secret('ERPNEXT_API_KEY'), secret('ERPNEXT_API_SECRET', 'env'),
      secret('GHN_TOKEN'), secret('GHTK_TOKEN'), secret('OPENAI_API_KEY'),
      secret('NEW_TOKEN', 'trong', false),
      {khoa:'ERPNEXT_URL', nhan:'URL', hien:'http://erp.test:8080', nguon:'env'},
      {khoa:'GHN_SHOP_ID', nhan:'Shop ID', hien:'12345', nguon:'env'}];
    window.render = () => {
      document.querySelector('#root').innerHTML = '<section data-kntt-dv="erpnext">'
        + fields.map(knttO).join('')
        + '<button data-kntt-luu="erpnext">Lưu</button>'
        + '<button data-kntt-kiem="erpnext">Kiểm tra</button>'
        + '<span data-kntt-kq="erpnext"></span></section>';
    };
    render();
    knttGanSuKien(document.querySelector('#root'), async () => render());
  });
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const checks = [];
  for (const key of ['ERPNEXT_API_KEY','ERPNEXT_API_SECRET','GHN_TOKEN','GHTK_TOKEN','OPENAI_API_KEY']) {
    const input = page.locator(`[data-kntt-khoa="${key}"]`);
    assert(!(await input.isVisible()) && await input.isDisabled(), key + ': saved field must be locked');
    assert(await input.inputValue() === '', key + ': mask must not be an input value');
    assert(await page.getByRole('button', {name:'Chỉnh sửa '+key, exact:true}).isVisible(), key + ': edit visible');
  }
  assert(await page.getByText('Đã lưu', {exact:true}).count() === 5, 'saved badges');
  checks.push('saved secrets masked and locked across five fields');
  assert(await page.locator('[data-kntt-khoa="ERPNEXT_URL"]').inputValue() === 'http://erp.test:8080', 'URL visible');
  assert(await page.locator('[data-kntt-khoa="GHN_SHOP_ID"]').inputValue() === '12345', 'shop visible');
  checks.push('non-sensitive values retained');
  await page.locator('[data-kntt-luu]').click();
  assert(await page.evaluate(() => requests.length) === 0, 'unchanged save must not send');
  await page.locator('[data-kntt-kiem]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{}', 'check uses saved secrets');
  checks.push('unchanged save/check omit credentials');
  await page.getByRole('button', {name:'Chỉnh sửa ERPNEXT_API_SECRET', exact:true}).click();
  const editor = page.locator('[data-kntt-khoa="ERPNEXT_API_SECRET"]');
  assert(await editor.isVisible() && await editor.isEnabled(), 'edit opens empty input');
  await page.locator('[data-kntt-kiem]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{}', 'blank edit preserves existing');
  await editor.fill('fake-new-secret');
  await page.locator('[data-kntt-kiem]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{"ERPNEXT_API_SECRET":"fake-new-secret"}', 'check new secret only');
  checks.push('edit and check only send newly typed value');
  await page.getByRole('button', {name:'Hủy chỉnh sửa', exact:true}).click();
  assert(await editor.inputValue() === '' && !(await editor.isVisible()), 'cancel discards unsaved text');
  await page.locator('[data-kntt-kiem]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{}', 'cancel preserves backend secret');
  checks.push('cancel restores saved display and omits replacement');
  await page.getByRole('button', {name:'Chỉnh sửa ERPNEXT_API_KEY', exact:true}).click();
  await page.locator('[data-kntt-khoa="ERPNEXT_API_KEY"]').fill('fake-replacement');
  await page.locator('[data-kntt-luu]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{"ERPNEXT_API_KEY":"fake-replacement"}', 'save only replacement');
  assert(!(await page.locator('[data-kntt-khoa="ERPNEXT_API_KEY"]').isVisible()), 'saved rerender locks input');
  checks.push('save refreshes saved display without sending masked/unchanged keys');
  await page.locator('[data-kntt-khoa="NEW_TOKEN"]').fill('fake-first-token');
  await page.locator('[data-kntt-luu]').click();
  assert(await page.evaluate(() => JSON.stringify(requests.at(-1).gia_tri)) === '{"NEW_TOKEN":"fake-first-token"}', 'first-time input');
  assert(!(await page.evaluate(() => JSON.stringify(requests))).includes('••••'), 'mask never sent');
  checks.push('first-time entry works; no mask in any request');
  return {passed:checks.length, checks};
}
