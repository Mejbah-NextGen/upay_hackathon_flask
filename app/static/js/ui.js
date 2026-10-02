(() => {
  'use strict';
  const dictionary = JSON.parse(document.getElementById('uiTranslations')?.textContent || '{}');
  window.upayT = text => dictionary[text] || text;
  const t = window.upayT;
  document.querySelectorAll('[data-language-select]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
  document.querySelectorAll('.theme-choice').forEach(button => button.addEventListener('click', () => {
    document.documentElement.dataset.theme = button.value;
  }));
  document.addEventListener('click', event => {
    document.querySelectorAll('.theme-dropdown[open]').forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') document.querySelectorAll('.theme-dropdown[open]').forEach(menu => { menu.open = false; menu.querySelector('summary').focus(); });
  });

  document.querySelectorAll('[data-operation-qr]').forEach(panel => {
    const form = panel.closest('form') || panel.closest('.form-page-grid')?.querySelector('form[data-wallet-operation]');
    const image = panel.querySelector('[data-qr-image]');
    const status = panel.querySelector('[data-qr-status]');
    const referenceInput = () => form?.querySelector('[data-qr-reference], [data-recipient-number], [name="agent_number"], [name="account_no"], [name="account_number"], [name="recipient_mobile"]');
    const generate = () => {
      const params = new URLSearchParams({ kind: panel.dataset.qrKind,
        reference: referenceInput()?.value || image.dataset.reference || '',
        provider: form?.querySelector('[name="provider"], [name="operator"]')?.value || image.dataset.provider || '',
        category: form?.querySelector('[name="category"]')?.value || '',
        amount: form?.querySelector('[name="amount"]')?.value || image.dataset.amount || '',
        channel: form?.querySelector('[name="channel"]')?.value || '' });
      image.src = `${panel.dataset.qrUrl}?${params}`;
    };
    panel.querySelector('[data-qr-generate]').addEventListener('click', generate);
    panel.addEventListener('toggle', () => { if (panel.open && !image.hasAttribute('src')) generate(); });
    image.addEventListener('error', () => { status.textContent = t('Enter valid details and generate a new QR.'); image.removeAttribute('src'); });
    const applyResult = result => {
      if (result.kind !== panel.dataset.qrKind) throw new Error(t('Use a QR code for this operation.'));
      const channel = form?.querySelector('[name="channel"]')?.value || '';
      if (result.channel && channel && result.channel !== channel) throw new Error(t('Choose the matching channel before reading this QR.'));
      const lockedCategory = form?.querySelector('[data-bill-category-locked]');
      if (lockedCategory && result.category !== lockedCategory.value) throw new Error(t('QR provider does not match the selected category.'));
      const setValue = (input, value) => {
        if (!input || !value) return;
        if (input.tagName === 'SELECT' && !Array.from(input.options).some(option => option.value === value && !option.disabled)) throw new Error(t('QR provider does not match the selected category.'));
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      };
      setValue(form?.querySelector('[name="category"]'), result.category);
      setValue(form?.querySelector('[name="provider"], [name="operator"]'), result.provider);
      setValue(referenceInput(), result.reference);
      setValue(form?.querySelector('[name="amount"]'), result.amount);
      status.textContent = t('Form filled. Review all details before confirming.');
    };
    const applyCode = async code => {
      const response = await fetch(panel.dataset.qrVerify, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': panel.dataset.csrf }, body: JSON.stringify({ code }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to read QR.');
      applyResult(result);
    };
    panel.querySelector('[data-qr-read]').addEventListener('click', async () => {
      try { await applyCode(panel.querySelector('[data-qr-text]').value.trim()); }
      catch (error) { status.textContent = t(error.message); }
    });
    panel.querySelector('[data-qr-file]').addEventListener('change', async event => {
      const file = event.target.files[0];
      if (!file) return;
      let bitmap;
      try {
        if (file.size > 5 * 1024 * 1024) throw new Error(t('Choose an image under 5 MB.'));
        if (window.BarcodeDetector) {
          bitmap = await createImageBitmap(file);
          const results = await new BarcodeDetector({ formats: ['qr_code'] }).detect(bitmap);
          if (!results.length) throw new Error(t('No QR code found in this image.'));
          await applyCode(results[0].rawValue);
        } else {
          const data = new FormData(); data.append('image', file);
          const response = await fetch(panel.dataset.qrUpload, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': panel.dataset.csrf }, body: data });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Unable to read QR.');
          applyResult(result);
        }
      } catch (error) { status.textContent = t(error.message); }
      finally { bitmap?.close(); }
    });
  });

  const photo = document.querySelector('[data-photo-input]');
  const preview = document.querySelector('[data-photo-preview]');
  const editor = document.querySelector('[data-photo-editor]');
  let photoUrl;
  const updatePreview = () => {
    if (!preview) return;
    const crop = document.querySelector('[name="photo_fit"]')?.value === 'square';
    preview.style.objectFit = crop ? 'cover' : 'contain';
    preview.style.aspectRatio = crop ? '1' : 'auto';
    preview.style.objectPosition = `${document.querySelector('[name="crop_x"]')?.value || 50}% ${document.querySelector('[name="crop_y"]')?.value || 50}%`;
  };
  photo?.addEventListener('change', () => {
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    if (!photo.files[0]) { editor.hidden = true; return; }
    photoUrl = URL.createObjectURL(photo.files[0]); preview.src = photoUrl; editor.hidden = false;
    updatePreview();
  });
  document.querySelectorAll('[name="photo_fit"], [name="crop_x"], [name="crop_y"]').forEach(input => input.addEventListener('input', updatePreview));
  preview?.addEventListener('error', () => {
    preview.hidden = true;
    document.querySelector('[data-photo-status]').textContent = t('Preview unavailable in this browser. The server will decode supported formats when you save.');
  });
  preview?.addEventListener('load', () => { preview.hidden = false; document.querySelector('[data-photo-status]').textContent = ''; });
})();
