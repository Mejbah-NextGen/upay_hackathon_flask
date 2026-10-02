(() => {
  const translate = value => window.upayT ? window.upayT(value) : value;
  document.querySelectorAll('[data-add-money-form]').forEach(form => {
    const source = form.querySelector('[name="source"]');
    const holder = form.querySelector('[data-funding-holder]');
    const updateSource = () => {
      form.querySelectorAll('[data-funding-fields]').forEach(group => {
        const active = group.dataset.fundingFields === source.value;
        group.hidden = !active;
        group.querySelectorAll('input, select').forEach(input => {
          input.disabled = !active;
          input.required = active;
          input.setCustomValidity('');
        });
      });
      const needsHolder = source.value !== 'Agent';
      holder.hidden = !needsHolder;
      const input = holder.querySelector('input');
      input.disabled = !needsHolder;
      input.required = needsHolder;
    };
    const card = form.querySelector('[name="card_number"]');
    const validateCard = () => {
      if (card.disabled || !card.value) { card.setCustomValidity(''); return; }
      const number = card.value.trim().replace(/[ -]/g, '');
      let checksum = 0;
      if (/^[0-9]{13,19}$/.test(number)) {
        Array.from(number).reverse().forEach((digit, index) => {
          let value = Number(digit);
          if (index % 2) { value *= 2; if (value > 9) value -= 9; }
          checksum += value;
        });
      }
      const valid = /^[0-9]{13,19}$/.test(number) && new Set(number).size > 1 && checksum % 10 === 0;
      card.setCustomValidity(valid ? '' : translate('Enter a valid demo card number. Sample: 4111 1111 1111 1111.'));
    };
    source.addEventListener('change', () => { updateSource(); validateCard(); });
    card.addEventListener('input', validateCard);
    updateSource();
  });

  document.querySelectorAll('[data-recharge-validation]').forEach(form => {
    const operator = form.querySelector('[name="operator"]');
    const mobile = form.querySelector('[name="mobile"]');
    const status = form.querySelector('[data-recharge-operator-status]');
    const prefixes = JSON.parse(form.dataset.operatorPrefixes);
    const checkOperator = () => {
      let number = mobile.value.trim().replace(/[\s()\-]/g, '');
      if (number.startsWith('+88')) number = number.slice(3);
      else if (number.startsWith('88') && number.length === 13) number = number.slice(2);
      let message = '';
      const expected = Object.keys(prefixes).find(name => prefixes[name].includes(number.slice(0, 3)));
      if (number.length >= 3 && /^01[0-9]/.test(number)) {
        if (!expected) message = 'Choose a supported recharge number beginning with 013–019.';
        else if (operator.value && operator.value !== expected) message = `This demo number begins with ${number.slice(0, 3)}. Choose ${expected} for this recharge.`;
      }
      operator.setCustomValidity(translate(message));
      status.textContent = translate(message || (expected ? `Number prefix ${number.slice(0, 3)}: ${expected}.` : 'The selected operator must match the number prefix in this demo.'));
      status.dataset.state = message ? 'invalid' : '';
    };
    operator.addEventListener('change', checkOperator);
    mobile.addEventListener('input', checkOperator);
    checkOperator();
  });

  document.querySelectorAll('[data-wallet-operation]').forEach(form => {
    const amount = form.querySelector('[name="amount"]');
    const rail = form.querySelector('[name="rail"]');
    const preview = form.querySelector('.wallet-quote');
    const status = form.querySelector('[data-wallet-quote-status]');
    if (!amount || !preview || !status) return;
    const fields = ['principal', 'fee', 'total', 'remaining'];
    let timer, controller, revision = 0;
    const text = value => window.upayT ? window.upayT(value) : value;
    const reset = message => {
      fields.forEach(key => { if (key !== 'remaining') form.querySelector(`[data-wallet-${key}]`).textContent = '৳ —'; });
      form.querySelector('[data-wallet-remaining]').textContent = `৳ ${Number(preview.dataset.walletBalance).toFixed(2)}`;
      status.textContent = text(message);
    };
    const update = () => {
      const current = ++revision;
      clearTimeout(timer);
      controller?.abort();
      if (!amount.value) {
        preview.dataset.state = '';
        reset('Enter an amount to see your exact fee and remaining balance.');
        return;
      }
      status.textContent = text('Calculating fee and remaining balance...');
      timer = setTimeout(async () => {
        const quoteController = new AbortController();
        controller = quoteController;
        const timeout = setTimeout(() => quoteController.abort(), 10000);
        const params = new URLSearchParams({ operation: form.dataset.walletOperation, channel: form.dataset.walletChannel, amount: amount.value, rail: rail?.value || 'NPSB' });
        try {
          const response = await fetch(`${form.dataset.walletQuote}?${params}`, { credentials: 'same-origin', signal: quoteController.signal, headers: { Accept: 'application/json' } });
          const result = await response.json();
          if (current !== revision) return;
          if (!response.ok) throw new Error(result.error || 'Unable to calculate this amount.');
          const keys = { principal: 'amount', fee: 'fee', total: 'total', remaining: 'remaining' };
          fields.forEach(key => { form.querySelector(`[data-wallet-${key}]`).textContent = `৳ ${Number(result[keys[key]]).toLocaleString('en-BD', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; });
          preview.dataset.state = result.can_submit ? 'ready' : 'error';
          status.textContent = text(result.can_submit ? 'Review your destination and total before confirming.' : 'Insufficient balance including the service fee.');
        } catch (error) {
          if (current !== revision) return;
          preview.dataset.state = 'error';
          reset(error.name === 'AbortError' ? 'Fee preview timed out. Enter the amount again to retry.' : error instanceof SyntaxError ? 'Unable to calculate this amount. Please refresh.' : error.message);
        } finally {
          clearTimeout(timeout);
        }
      }, 180);
    };
    amount.addEventListener('input', update);
    rail?.addEventListener('change', update);
    update();
  });
})();
