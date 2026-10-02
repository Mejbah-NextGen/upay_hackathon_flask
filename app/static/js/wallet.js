(() => {
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
