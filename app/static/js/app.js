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

  document.querySelectorAll('[data-recipient-form="schedule"]').forEach(form => {
    const kind = form.querySelector('[name="kind"]');
    const category = form.querySelector('[name="category"]');
    const provider = form.querySelector('[name="provider"]');
    const number = form.querySelector('[data-recipient-number]');
    const updateScheduleOperation = () => {
      if (!kind || !category || !provider) return;
      form.dataset.recipientKind = kind.value;
      const bill = kind.value === 'BILL_PAYMENT';
      const transfer = kind.value === 'SEND_MONEY';
      category.disabled = !bill;
      category.required = bill;
      const categoryField = form.querySelector('[data-schedule-category-field]');
      if (categoryField) categoryField.hidden = !bill;
      if (bill && !category.value) category.value = Array.from(category.options).find(option => option.value)?.value || '';
      provider.disabled = transfer;
      provider.required = !transfer;
      const providerField = form.querySelector('[data-schedule-provider-field]');
      if (providerField) providerField.hidden = transfer;
      Array.from(provider.options).forEach(option => {
        const allowed = !option.value || (option.dataset.kind === kind.value && (!bill || option.dataset.category === category.value));
        option.disabled = !allowed;
        option.hidden = !allowed;
      });
      Array.from(provider.querySelectorAll('optgroup')).forEach(group => {
        group.hidden = !Array.from(group.children).some(option => !option.disabled);
      });
      if (transfer) provider.value = '';
      else if (!provider.value || provider.selectedOptions[0]?.disabled) provider.value = Array.from(provider.options).find(option => option.value && !option.disabled)?.value || '';
      const numberLabel = form.querySelector('[data-schedule-recipient-label]');
      if (numberLabel) numberLabel.textContent = bill ? 'Bill account / Payment reference' : 'Recipient mobile number';
      if (number) {
        number.placeholder = bill ? 'DEMO-METER-1001' : '01XXXXXXXXX';
        number.inputMode = bill ? 'text' : 'tel';
        number.maxLength = bill ? 60 : 24;
      }
    };
    kind?.addEventListener('change', updateScheduleOperation);
    category?.addEventListener('change', updateScheduleOperation);
    updateScheduleOperation();

    const dueDate = form.querySelector('[name="due_date"]');
    const frequency = form.querySelector('[name="frequency"]');
    const amount = form.querySelector('[name="amount"]');
    const autoPay = form.querySelector('[name="auto_pay"]');
    const preview = form.querySelector('[data-schedule-preview]');
    const updateSchedulePreview = () => {
      if (!dueDate || !frequency || !amount || !preview) return;
      const inputDate = dueDate.value;
      const cents = Math.round(Number(amount.value) * 100);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(inputDate) || inputDate < dueDate.min || inputDate > dueDate.max || !Number.isFinite(cents) || cents <= 0 || cents > 10000000) {
        preview.textContent = 'Choose a valid date and amount to preview your payment installments. No balance is deducted when you save a plan.';
        return;
      }
      const [year, month, originalDay] = inputDate.split('-').map(Number);
      const dates = [inputDate];
      if (frequency.value === 'MONTHLY') {
        for (let offset = 1; offset <= 3; offset += 1) {
          const lastDay = new Date(Date.UTC(year, month - 1 + offset + 1, 0)).getUTCDate();
          const nextDate = new Date(Date.UTC(year, month - 1 + offset, Math.min(originalDay, lastDay))).toISOString().slice(0, 10);
          if (nextDate > dueDate.max) break;
          dates.push(nextDate);
        }
      }
      const labels = dates.map(value => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)));
      const total = (cents * dates.length / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      preview.textContent = `${dates.length} installment${dates.length === 1 ? '' : 's'}: ${labels.join(' · ')}. Planned total: BDT ${total}. ${autoPay?.value === '0' ? 'Manual payment when due.' : 'Auto Pay when due.'} Saving this plan does not deduct balance.`;
    };
    [dueDate, frequency, amount, autoPay].forEach(input => {
      input?.addEventListener('input', updateSchedulePreview);
      input?.addEventListener('change', updateSchedulePreview);
    });
    updateSchedulePreview();
  });

  document.querySelectorAll('[data-recipient-lookup]').forEach(form => {
    const number = form.querySelector('[data-recipient-number]');
    const status = form.querySelector('[data-recipient-status]');
    if (!number || !status) return;
    const initialText = status.textContent;
    const submitButtons = Array.from(form.querySelectorAll('button[type="submit"]')).filter(button => button.value !== 'choose-category');
    let timer, controller, generation = 0;
    const setStatus = (text, state = '') => {
      status.textContent = text;
      status.dataset.state = state;
      number.setAttribute('aria-invalid', String(state === 'blocked' || state === 'invalid'));
      submitButtons.forEach(button => { button.disabled = state === 'blocked'; });
    };
    const check = async revision => {
      const params = new URLSearchParams({ kind: form.dataset.recipientKind, number: number.value.trim() });
      const provider = form.querySelector('[name="provider"], [name="operator"]');
      const category = form.querySelector('[name="category"]');
      if (provider) params.set('provider', provider.value);
      if (category) params.set('category', category.value);
      const currentController = new AbortController();
      controller = currentController;
      const timeout = setTimeout(() => currentController.abort(), 10000);
      setStatus('Checking recipient...', 'loading');
      try {
        const response = await fetch(`${form.dataset.recipientLookup}?${params}`, {
          signal: currentController.signal, headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'same-origin'
        });
        if (revision !== generation) return;
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('lookup');
        const result = await response.json();
        if (!response.ok && !(response.status === 400 && result.status === 'invalid')) throw new Error('lookup');
        if (revision !== generation) return;
        const description = result.status === 'blocked' ? 'Blocked number. This recipient cannot transact.'
          : result.status === 'registered' ? `Registered: ${result.name || result.authorization_name || 'Verified account'}`
          : result.status === 'invalid' ? (result.message || 'Enter a valid recipient number or reference.')
          : 'Not registered. No verified name exists in this project directory.';
        const authority = result.authorization_name && result.authorization_name !== result.name ? ` Authorizing provider: ${result.authorization_name}.` : '';
        setStatus(description + authority, result.status);
      } catch (error) {
        if (revision !== generation) return;
        setStatus('Recipient check is unavailable. Check your connection; the server will validate when you submit.', 'unavailable');
      } finally {
        clearTimeout(timeout);
      }
    };
    const queueCheck = () => {
      generation += 1;
      const revision = generation;
      clearTimeout(timer);
      controller?.abort();
      setStatus(initialText);
      const minLength = form.dataset.recipientKind === 'BILL_PAYMENT' ? 2 : 6;
      if (number.value.trim().length < minLength) return;
      timer = setTimeout(() => check(revision), 350);
    };
    number.addEventListener('input', queueCheck);
    form.querySelectorAll('[name="provider"], [name="operator"], [name="category"], [name="kind"]').forEach(input => input.addEventListener('change', () => {
      if (input.name === 'kind') form.dataset.recipientKind = input.value;
      queueCheck();
    }));
    queueCheck();
  });

  const assistantDialog = document.getElementById('assistantDialog');
  const assistantToggle = document.getElementById('assistantToggle');
  const assistantForm = document.getElementById('assistantForm');
  const question = document.getElementById('assistantQuestion');
  const messages = document.getElementById('assistantMessages');
  const assistantStatus = document.getElementById('assistantStatus');
  const assistantSend = document.getElementById('assistantSend');
  const assistantClear = document.getElementById('assistantClear');
  const promptButtons = Array.from(document.querySelectorAll('[data-assistant-prompt]'));
  let conversation = [], assistantBusy = false;
  const appendMessage = (label, content, role, links = []) => {
    const bubble = document.createElement('div');
    bubble.className = `assistant-message assistant-message-${role}`;
    const title = document.createElement('strong');
    title.textContent = label;
    const text = document.createElement('p');
    text.textContent = content;
    bubble.append(title, text);
    if (links.length) {
      const actions = document.createElement('div');
      actions.className = 'assistant-links';
      links.forEach(link => {
        if (typeof link.url !== 'string' || !link.url.startsWith('/') || link.url.startsWith('//')) return;
        const action = document.createElement('a');
        action.href = link.url;
        action.className = 'btn btn-soft';
        action.textContent = link.label;
        actions.append(action);
      });
      bubble.append(actions);
    }
    messages?.append(bubble);
    if (messages) messages.scrollTop = messages.scrollHeight;
    return bubble;
  };
  const setAssistantBusy = busy => {
    assistantBusy = busy;
    if (assistantSend) { assistantSend.disabled = busy; assistantSend.textContent = busy ? 'Sending...' : 'Send'; }
    if (question) question.disabled = busy;
    if (assistantClear) assistantClear.disabled = busy;
    promptButtons.forEach(button => { button.disabled = busy; });
    messages?.setAttribute('aria-busy', String(busy));
  };
  assistantToggle?.addEventListener('click', event => {
    if (!assistantDialog?.showModal) return;
    event.preventDefault();
    if (notifications?.open) notifications.open = false;
    closeMenu();
    if (!assistantDialog.open) assistantDialog.showModal();
    assistantToggle.setAttribute('aria-expanded', 'true');
    question?.focus();
  });
  document.getElementById('assistantClose')?.addEventListener('click', () => assistantDialog?.close());
  assistantDialog?.addEventListener('close', () => {
    assistantToggle?.setAttribute('aria-expanded', 'false');
    assistantToggle?.focus();
  });
  assistantDialog?.addEventListener('click', event => {
    if (event.target !== assistantDialog) return;
    const bounds = assistantDialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) assistantDialog.close();
  });
  assistantForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const prompt = question?.value.trim();
    if (!prompt || assistantBusy) return;
    setAssistantBusy(true);
    assistantStatus.textContent = 'Reading your app information...';
    const userBubble = appendMessage('You', prompt, 'user');
    const currentController = new AbortController();
    const timeout = setTimeout(() => currentController.abort(), 25000);
    try {
      const response = await fetch(assistantDialog.dataset.endpoint, {
        method: 'POST', credentials: 'same-origin', signal: currentController.signal,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': assistantDialog.dataset.csrf },
        body: JSON.stringify({ question: prompt, history: conversation.slice(-8) })
      });
      const jsonResponse = response.headers.get('content-type')?.includes('application/json');
      const result = jsonResponse ? await response.json() : {};
      if (!response.ok) throw new Error(result.error || (response.status === 400 ? 'Your session token expired. Refresh this page and try again.' : 'The assistant is unavailable. Try again shortly.'));
      if (typeof result.answer !== 'string') throw new Error('The assistant could not answer. Try again.');
      appendMessage(result.mode_label || 'App Assistant', result.answer, 'guide', result.links || []);
      conversation.push({ role: 'user', content: prompt }, { role: 'assistant', content: result.answer });
      conversation = conversation.slice(-8);
      question.value = '';
      assistantStatus.textContent = result.notice || `${result.mode_label || 'App Assistant'} answered using your demo app information.`;
    } catch (error) {
      userBubble.remove();
      assistantStatus.textContent = error.name === 'AbortError' ? 'The assistant timed out. Your question is saved below; try again.' : error.message;
    } finally {
      clearTimeout(timeout);
      setAssistantBusy(false);
      if (assistantDialog.open) question.focus();
    }
  });
  question?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      assistantForm?.requestSubmit();
    }
  });
  promptButtons.forEach(button => button.addEventListener('click', () => {
    if (!question || assistantBusy) return;
    question.value = button.dataset.assistantPrompt;
    assistantForm?.requestSubmit();
  }));
  assistantClear?.addEventListener('click', () => {
    if (assistantBusy) return;
    conversation = [];
    messages?.querySelectorAll('.assistant-message:not(:first-child)').forEach(message => message.remove());
    assistantStatus.textContent = 'Chat cleared.';
    question.value = '';
    question.focus();
  });
})();
