(() => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const toggle = document.getElementById('menuToggle');
  const openMenu = () => {
    if (!sidebar) return;
    sidebar.classList.add('open');
    overlay?.classList.add('show');
    toggle?.setAttribute('aria-expanded', 'true');
    sidebar.querySelector('a')?.focus();
  };
  const closeMenu = () => {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('show');
    toggle?.setAttribute('aria-expanded', 'false');
  };
  toggle?.addEventListener('click', () => sidebar?.classList.contains('open') ? closeMenu() : openMenu());
  overlay?.addEventListener('click', () => { closeMenu(); toggle?.focus(); });
  sidebar?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));

  const notifications = document.getElementById('notificationDropdown');
  const notificationToggle = notifications?.querySelector('summary');
  notifications?.addEventListener('toggle', () => {
    notificationToggle?.setAttribute('aria-expanded', String(notifications.open));
  });
  document.addEventListener('click', event => {
    if (notifications?.open && !notifications.contains(event.target)) notifications.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (notifications?.open) { notifications.open = false; notificationToggle?.focus(); }
      if (sidebar?.classList.contains('open')) { closeMenu(); toggle?.focus(); }
    }
    if (event.key === 'Tab' && sidebar?.classList.contains('open')) {
      const links = Array.from(sidebar.querySelectorAll('a, button'));
      const first = links[0];
      const last = links[links.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });

  document.querySelectorAll('[data-amount]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.querySelector('input[name="amount"]');
      if (input) {
        input.value = btn.dataset.amount;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
  });

  const billCategory = document.querySelector('[data-bill-category]');
  const billProvider = document.querySelector('[data-bill-provider]');
  const updateBillCategory = () => {
    if (!billCategory || !billProvider) return;
    const selected = billCategory.selectedOptions[0];
    let providerIsAllowed = false;
    Array.from(billProvider.options).forEach(option => {
      const allowed = !option.value || option.dataset.category === billCategory.value;
      option.hidden = !allowed;
      option.disabled = !allowed;
      if (option.selected && allowed) providerIsAllowed = true;
    });
    if (!providerIsAllowed) billProvider.value = '';
    const heading = document.querySelector('[data-bill-heading]');
    const accountLabel = document.querySelector('[data-bill-account-label]');
    if (heading && selected?.dataset.heading) heading.textContent = selected.dataset.heading;
    if (accountLabel && selected?.dataset.accountLabel) accountLabel.textContent = selected.dataset.accountLabel;
  };
  billCategory?.addEventListener('change', updateBillCategory);
  updateBillCategory();

  const cashOut = document.querySelector('[data-cash-out]');
  const cashAmount = cashOut?.querySelector('input[name="amount"]');
  const cashSummary = cashOut?.querySelector('[data-cash-out-summary]');
  const updateCashFee = () => {
    if (!cashAmount || !cashSummary) return;
    const amount = Number(cashAmount.value);
    const cents = Number.isFinite(amount) && amount > 0 && amount <= 100000 ? Math.round(amount * 100) : 0;
    const feeCents = Math.round(cents * 15 / 1000);
    cashSummary.textContent = `Fee: \u09f3 ${(feeCents / 100).toFixed(2)} \u00b7 Total deduction: \u09f3 ${((cents + feeCents) / 100).toFixed(2)}`;
  };
  cashAmount?.addEventListener('input', updateCashFee);
  updateCashFee();
})();
