(() => {
  'use strict';
  const source = document.getElementById('reportChartData');
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const labels = JSON.parse(document.getElementById('reportChartLabels').textContent);
  const dialog = document.getElementById('reportSegmentDialog');
  const hover = document.getElementById('reportSegmentTooltip');
  const ns = 'http://www.w3.org/2000/svg';
  const colors = {incoming: '#17a769', outgoing: '#0b63ce', net: '#a276ef'};
  const money = value => `BDT ${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  const translate = value => typeof window.upayT === 'function' ? window.upayT(value) : value;
  const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 1, notation: Math.abs(value) >= 10000 ? 'compact' : 'standard'});
  const node = (name, attributes = {}, content) => {
    const item = document.createElementNS(ns, name);
    Object.entries(attributes).forEach(([key, value]) => item.setAttribute(key, value));
    if (content !== undefined) item.textContent = content;
    return item;
  };
  const append = (parent, name, attributes, content) => {
    const item = node(name, attributes, content); parent.append(item); return item;
  };
  const tooltip = (item, text) => {item.setAttribute('aria-label', text); append(item, 'title', {}, text);};
  const empty = target => {
    const p = document.createElement('p'); p.className = 'report-chart-empty'; p.textContent = labels.empty;
    document.getElementById(target).append(p);
  };
  const selectedRows = selection => data.transactions.filter(tx => {
    if (selection.mode === 'daily' || selection.mode === 'cumulative') {
      return tx.date <= selection.end && (selection.mode !== 'daily' || tx.date >= selection.start) &&
        (!selection.direction || tx.direction === selection.direction);
    }
    if (selection.mode === 'category') {
      return tx.direction === 'OUT' && tx.kind === selection.kind && tx.category === (selection.category || '');
    }
    const deduction = -tx.change;
    return tx.direction === 'OUT' && deduction >= selection.lower && (selection.upper === null || deduction < selection.upper);
  });
  let returnFocus = null;
  const hideTooltip = () => {hover.hidden = true;};
  const openSelection = (title, selection) => {
    hideTooltip();
    const rows = selectedRows(selection);
    document.getElementById('reportSegmentTitle').textContent = title;
    const incoming = rows.filter(tx => tx.direction === 'IN').reduce((total, tx) => total + tx.change, 0);
    const outgoing = rows.filter(tx => tx.direction === 'OUT').reduce((total, tx) => total - tx.change, 0);
    const fees = rows.filter(tx => tx.direction === 'OUT').reduce((total, tx) => total + tx.fee, 0);
    document.getElementById('reportSegmentSummary').textContent = `${rows.length} ${labels.selected}. ${labels.incoming}: ${money(incoming)} · ${labels.outgoing}: ${money(outgoing)} · ${labels.fees}: ${money(fees)}`;
    document.getElementById('reportSegmentSelection').value = JSON.stringify(selection);
    document.getElementById('reportSegmentExport').disabled = rows.length === 0;
    const body = document.getElementById('reportSegmentRows'); body.replaceChildren();
    rows.forEach(tx => {
      const tr = document.createElement('tr');
      [tx.datetime, translate(tx.title), tx.counterparty, money(tx.amount), money(tx.fee), money(tx.change)].forEach(value => {
        const td = document.createElement('td'); td.textContent = value; tr.append(td);
      });
      const td = document.createElement('td');
      if (tx.id !== null) {
        const link = document.createElement('a'); link.className = 'inline-link';
        link.href = dialog.dataset.receiptUrl.replace(/\/0$/, `/${tx.id}`); link.textContent = labels.receipt;
        td.append(link);
        if (tx.reference) {const reference = document.createElement('small'); reference.className = 'muted'; reference.textContent = tx.reference; td.append(document.createElement('br'), reference);}
      }
      tr.append(td); body.append(tr);
    });
    if (!rows.length) {
      const tr = document.createElement('tr'), td = document.createElement('td'); td.colSpan = 7; td.textContent = labels.noRows; tr.append(td); body.append(tr);
    }
    returnFocus = document.activeElement;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('[data-report-close]').focus();
  };
  dialog.querySelector('[data-report-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {hideTooltip(); if (returnFocus?.isConnected) returnFocus.focus({preventScroll: true});});
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
  const interactive = (item, text, title, selection) => {
    item.setAttribute('tabindex', '0'); item.setAttribute('role', 'button');
    item.setAttribute('aria-label', `${text}. ${labels.details}`); item.setAttribute('aria-haspopup', 'dialog');
    item.setAttribute('aria-controls', dialog.id); item.setAttribute('data-chart-segment', selection.mode);
    const preview = event => {
      if (dialog.open || event.pointerType === 'touch') return;
      hover.textContent = `${text}\n${labels.details}`; hover.hidden = false;
      const rect = item.getBoundingClientRect();
      const x = event.clientX || rect.left + rect.width / 2, y = event.clientY || rect.top;
      hover.style.left = `${Math.max(8, Math.min(x + 12, window.innerWidth - hover.offsetWidth - 8))}px`;
      hover.style.top = `${Math.max(8, Math.min(y + 14, window.innerHeight - hover.offsetHeight - 8))}px`;
    };
    item.addEventListener('pointerenter', preview); item.addEventListener('focus', preview);
    item.addEventListener('pointerleave', hideTooltip); item.addEventListener('blur', hideTooltip);
    item.addEventListener('click', () => openSelection(title, selection));
    item.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); openSelection(title, selection);}
    });
  };
  const compactViewport = window.matchMedia('(max-width: 620px)');
  const render = () => {
    hideTooltip();
    ['reportBarChart', 'reportCumulativeChart', 'reportPieChart', 'reportHistogramChart', 'reportPieLegend'].forEach(id => document.getElementById(id).replaceChildren());
    const chart = (target, values, minimum = 0) => {
      const svg = append(document.getElementById(target), 'svg', {viewBox: '0 0 600 300', role: 'group'});
      const low = Math.min(minimum, ...values), high = Math.max(1, ...values), range = high - low || 1;
      const y = value => 250 - (value - low) / range * 215;
      for (let i = 0; i <= 4; i++) {
        const value = low + range * i / 4, position = y(value);
        append(svg, 'line', {x1: 66, x2: 550, y1: position, y2: position, class: 'chart-grid'});
        append(svg, 'text', {x: 59, y: position + 4, 'text-anchor': 'end', 'font-size': 12, class: 'chart-axis-text'}, number(value));
      }
      append(svg, 'line', {x1: 66, x2: 550, y1: y(0), y2: y(0), stroke: 'var(--muted)', 'stroke-width': 1});
      return {svg, y, left: 66, right: 550};
    };
    const barRows = [], groupSize = Math.max(1, Math.ceil(data.daily.length / (compactViewport.matches ? 5 : 10)));
    for (let i = 0; i < data.daily.length; i += groupSize) {
      const rows = data.daily.slice(i, i + groupSize);
      barRows.push({start: rows[0].date, end: rows[rows.length - 1].date, incoming: rows.reduce((s, r) => s + r.incoming, 0), outgoing: rows.reduce((s, r) => s + r.outgoing, 0)});
    }
    const bars = chart('reportBarChart', barRows.flatMap(row => [row.incoming, row.outgoing]));
    const step = (bars.right - bars.left) / Math.max(1, barRows.length);
    barRows.forEach((row, i) => {
      const center = bars.left + step * (i + .5), width = Math.min(20, step * .32);
      const range = `${row.start}${row.end !== row.start ? ' – ' + row.end : ''}`;
      ['incoming', 'outgoing'].forEach((key, k) => {
        const rect = append(bars.svg, 'rect', {x: center + (k - 1) * width, y: bars.y(row[key]), width: Math.max(2, width - 2), height: Math.max(0, bars.y(0) - bars.y(row[key])), fill: colors[key], rx: 2});
        interactive(rect, `${range}: ${labels[key]} ${money(row[key])}`, `${labels[key]} · ${range}`, {mode: 'daily', start: row.start, end: row.end, direction: key === 'incoming' ? 'IN' : 'OUT'});
      });
      tooltip(append(bars.svg, 'text', {x: center, y: 273, 'font-size': 11, 'text-anchor': 'middle', class: 'chart-axis-text'}, row.start.slice(5)), range);
    });
    append(bars.svg, 'text', {x: 550, y: 17, 'font-size': 12, 'text-anchor': 'end', class: 'chart-axis-text'}, 'BDT');
    const cumulative = chart('reportCumulativeChart', [0, ...data.daily.flatMap(row => [row.cumulative_incoming, row.cumulative_outgoing, row.cumulative_net])]);
    const first = Date.parse(data.daily[0].date), last = Date.parse(data.daily[data.daily.length - 1].date), span = last - first;
    const xAt = row => span ? 100 + (Date.parse(row.date) - first) / span * 450 : 550;
    ['incoming', 'outgoing', 'net'].forEach(key => {
      const field = `cumulative_${key}`, points = [[66, cumulative.y(0)], ...data.daily.map(row => [xAt(row), cumulative.y(row[field])])];
      append(cumulative.svg, 'polyline', {points: points.map(p => p.join(',')).join(' '), fill: 'none', stroke: colors[key], 'stroke-width': 3, 'pointer-events': 'none'});
      data.daily.forEach(row => {
        const circle = append(cumulative.svg, 'circle', {cx: xAt(row), cy: cumulative.y(row[field]), r: 6, fill: colors[key]});
        interactive(circle, `${row.date}: ${labels[key]} ${money(row[field])}`, `${labels[key]} · ${labels.through} ${row.date}`, {mode: 'cumulative', end: row.date, direction: key === 'incoming' ? 'IN' : key === 'outgoing' ? 'OUT' : ''});
      });
    });
    append(cumulative.svg, 'text', {x: 66, y: 273, 'font-size': 11, class: 'chart-axis-text'}, data.daily[0].date);
    append(cumulative.svg, 'text', {x: 550, y: 273, 'font-size': 11, 'text-anchor': 'end', class: 'chart-axis-text'}, data.daily[data.daily.length - 1].date);
    append(cumulative.svg, 'text', {x: 550, y: 17, 'font-size': 12, 'text-anchor': 'end', class: 'chart-axis-text'}, 'BDT');
    if (!data.outgoing_count) {empty('reportPieChart'); empty('reportHistogramChart'); return;}
    const palette = ['#0b63ce', '#17a769', '#a276ef', '#ef9550', '#e33d52', '#14a6a6', '#cc65ab', '#8b9a31'];
    const pie = append(document.getElementById('reportPieChart'), 'svg', {viewBox: '0 0 600 300', role: 'group'});
    const arcPoint = (radius, fraction) => [300 + radius * Math.cos(fraction * Math.PI * 2 - Math.PI / 2), 150 + radius * Math.sin(fraction * Math.PI * 2 - Math.PI / 2)];
    let offset = 0;
    data.categories.forEach((row, i) => {
      const percentage = row.amount / data.outgoing_total, color = palette[i % palette.length];
      const a = arcPoint(128, offset), b = arcPoint(128, offset + percentage), c = arcPoint(70, offset + percentage), d = arcPoint(70, offset);
      const large = percentage > .5 ? 1 : 0;
      const path = percentage >= .999999 ? 'M300 22 A128 128 0 1 1 300 278 A128 128 0 1 1 300 22 M300 80 A70 70 0 1 0 300 220 A70 70 0 1 0 300 80' :
        `M${a} A128 128 0 ${large} 1 ${b} L${c} A70 70 0 ${large} 0 ${d} Z`;
      const slice = append(pie, 'path', {d: path, fill: color, 'fill-rule': 'evenodd'});
      const title = translate(row.label), text = `${title}: ${money(row.amount)} (${(percentage * 100).toFixed(1)}%)`;
      const selection = {mode: 'category', kind: row.kind, category: row.category};
      interactive(slice, text, title, selection); offset += percentage;
      const legend = document.createElement('button'), swatch = document.createElement('i');
      legend.type = 'button'; swatch.className = 'chart-swatch'; swatch.style.background = color;
      legend.append(swatch, document.createTextNode(`${title} ${(percentage * 100).toFixed(1)}%`));
      interactive(legend, text, title, selection); document.getElementById('reportPieLegend').append(legend);
    });
    append(pie, 'text', {x: 300, y: 146, 'font-size': 14, 'text-anchor': 'middle', class: 'chart-axis-text', 'pointer-events': 'none'}, labels.outgoing);
    append(pie, 'text', {x: 300, y: 176, 'font-size': 19, 'font-weight': 700, 'text-anchor': 'middle', class: 'chart-total-text', 'pointer-events': 'none'}, money(data.outgoing_total));
    const histogram = chart('reportHistogramChart', [...data.histogram.map(row => row.count), Math.max(4, Math.ceil(Math.max(...data.histogram.map(row => row.count)) / 4) * 4)]);
    const histStep = (histogram.right - histogram.left) / data.histogram.length, linePoints = [];
    data.histogram.forEach((row, i) => {
      const center = histogram.left + histStep * (i + .5);
      const rect = append(histogram.svg, 'rect', {x: center - histStep * .29, y: histogram.y(row.count), width: histStep * .58, height: histogram.y(0) - histogram.y(row.count), fill: colors.outgoing, rx: 3});
      interactive(rect, `BDT ${row.label}: ${row.count} ${labels.transactions}`, `${labels.amountBand} · BDT ${row.label}`, {mode: 'amount', lower: row.lower, upper: row.upper});
      const percentageY = 250 - row.cumulative_percent / 100 * 215; linePoints.push([center, percentageY]);
      const circle = append(histogram.svg, 'circle', {cx: center, cy: percentageY, r: 6, fill: colors.net});
      interactive(circle, `BDT ${row.label}: ${row.cumulative_percent}% ${labels.cumulative}`, `${labels.cumulative} · BDT ${row.upper === null ? 'All amounts' : '0–<' + row.upper.toLocaleString()}`, {mode: 'amount', lower: 0, upper: row.upper});
      const bound = value => value >= 1000 ? `${value / 1000}k` : String(value);
      const shortLabel = row.upper === null ? `${bound(row.lower)}+` : `${bound(row.lower)}–${bound(row.upper)}`;
      tooltip(append(histogram.svg, 'text', {x: center, y: 274, 'font-size': 10, 'text-anchor': 'middle', class: 'chart-axis-text chart-band-text'}, shortLabel), `BDT ${row.label}`);
    });
    append(histogram.svg, 'polyline', {points: linePoints.map(point => point.join(',')).join(' '), fill: 'none', stroke: colors.net, 'stroke-width': 3, 'pointer-events': 'none'});
    for (let percent = 0; percent <= 100; percent += 25) append(histogram.svg, 'text', {x: 596, y: 254 - percent / 100 * 215, 'font-size': 11, 'text-anchor': 'end', class: 'chart-axis-text chart-percent-text'}, `${percent}%`);
  };
  render(); compactViewport.addEventListener('change', render);
})();