(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root = document.documentElement;

  /* ---------- three-dot menu ---------- */
  var dotsBtn = $('#dotsBtn'), dotsMenu = $('#dotsMenu');
  dotsBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    var open = dotsMenu.hidden;
    dotsMenu.hidden = !open;
    dotsBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', function () { dotsMenu.hidden = true; dotsBtn.setAttribute('aria-expanded', 'false'); });

  /* ---------- video sections: lazy-load, play only the one in view ---------- */
  var vids = $$('.vid video');
  function load(v) { if (!v.src && v.dataset.src) { v.src = v.dataset.src; v.load(); } }
  var loader = new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) load(e.target); });
  }, { rootMargin: '150% 0px' });
  var player = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      var v = e.target, panel = v.parentElement;
      if (e.isIntersecting) {
        load(v);
        panel.classList.add('on');
        var p = v.play(); if (p && p.catch) p.catch(function () {});
      } else {
        panel.classList.remove('on');
        v.pause();
        try { v.currentTime = 0; } catch (_) {}   // each video restarts from its first frame
      }
    });
  }, { threshold: 0.55 });
  vids.forEach(function (v) { loader.observe(v); player.observe(v); });

  /* ---------- call / WhatsApp chooser ---------- */
  var WA_TEXT = encodeURIComponent('Hello Yash Caterers, I would like to enquire about your catering services.');
  var sheet = $('#sheet');
  $$('.num').forEach(function (b) {
    b.addEventListener('click', function () {
      $('#sheetNum').textContent = b.dataset.phone;
      $('#sheetCall').href = 'tel:' + b.dataset.phone;
      $('#sheetWa').href = 'https://wa.me/' + b.dataset.wa + '?text=' + WA_TEXT;
      sheet.hidden = false;
    });
  });
  function closeSheet() { sheet.hidden = true; }
  $('#sheetClose').addEventListener('click', closeSheet);
  sheet.addEventListener('click', function (e) { if (e.target === sheet) closeSheet(); });
  $('#sheetCall').addEventListener('click', closeSheet);
  $('#sheetWa').addEventListener('click', closeSheet);

  /* ---------- enquiry modal ---------- */
  var modal = $('#enquiry'), form = $('#enqForm'), thanks = $('#thanks');
  function openModal() {
    modal.hidden = false; modal.scrollTop = 0; root.classList.add('lock');
    $('#bar').hidden = true;
  }
  function closeModal() {
    modal.hidden = true; root.classList.remove('lock'); $('#bar').hidden = false;
  }
  $$('[data-open-enquiry]').forEach(function (b) { b.addEventListener('click', openModal); });
  $('#enqClose').addEventListener('click', closeModal);
  $('#thanksClose').addEventListener('click', function () {
    closeModal(); resetForm();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if (!modal.hidden) closeModal(); closeSheet(); }
  });

  /* event type "Other" */
  form.event_type.addEventListener('change', function () {
    $('#otherTypeWrap').hidden = form.event_type.value !== 'Other';
  });

  /* people */
  var peopleSel = $('#peopleSel'), peopleCustom = $('#peopleCustom');
  peopleSel.addEventListener('change', function () {
    $('#peopleCustomWrap').hidden = peopleSel.value !== 'custom';
    if (peopleSel.value === 'custom') peopleCustom.focus();
  });
  function peopleValue() {
    if (peopleSel.value === 'custom') return peopleCustom.value.trim();
    return peopleSel.value;
  }

  /* ---------- food rows ---------- */
  var MENU = JSON.parse($('#menu-data').textContent);
  var UNITS = JSON.parse($('#unit-data').textContent);
  var rows = $('#rows');

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }

  function addRow() {
    var sel = el('select', { 'data-f': 'name', 'aria-label': 'Food item' });
    sel.appendChild(el('option', { value: '', text: 'Select food item' }));
    MENU.forEach(function (c) {
      var g = el('optgroup', { label: c.category });
      c.items.forEach(function (i) { g.appendChild(el('option', { value: i, text: i })); });
      sel.appendChild(g);
    });
    var qty = el('input', { 'data-f': 'quantity', type: 'number', inputmode: 'decimal', min: '0', step: 'any', placeholder: 'e.g. 2.5' });
    var unit = el('select', { 'data-f': 'unit', 'aria-label': 'Unit' });
    UNITS.forEach(function (u) { unit.appendChild(el('option', { value: u, text: u })); });
    var other = el('input', { 'data-f': 'unit_other', type: 'text', maxlength: '30', placeholder: 'Type your unit (e.g. buckets)', class: 'unit-other' });
    other.hidden = true;
    unit.addEventListener('change', function () { other.hidden = unit.value !== 'Other'; if (!other.hidden) other.focus(); });
    sel.addEventListener('change', refreshOptions);

    var rm = el('button', { type: 'button', class: 'rm', 'aria-label': 'Remove item', text: '×' });
    rm.addEventListener('click', function () {
      row.remove();
      if (!rows.children.length) addRow();
      refreshOptions();
    });
    var row = el('div', { class: 'row' }, [
      rm,
      el('label', { class: 'item-label' }, [document.createTextNode('Food Item'), sel]),
      el('div', { class: 'qty' }, [
        el('label', {}, [document.createTextNode('Quantity'), qty]),
        el('label', {}, [document.createTextNode('Unit'), unit])
      ]),
      el('label', {}, [other])
    ]);
    // the "other" label wrapper has no caption; keep spacing tidy
    row.lastChild.style.marginBottom = '0';
    rows.appendChild(row);
    refreshOptions();
    return row;
  }

  /* prevent choosing the same food item twice */
  function refreshOptions() {
    var chosen = $$('select[data-f=name]', rows).map(function (s) { return s.value; }).filter(Boolean);
    $$('select[data-f=name]', rows).forEach(function (s) {
      $$('option', s).forEach(function (o) {
        o.disabled = !!o.value && o.value !== s.value && chosen.indexOf(o.value) !== -1;
      });
    });
  }
  $('#addRow').addEventListener('click', function () {
    var r = addRow(); r.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  function collectItems() {
    return $$('.row', rows).map(function (r) {
      var g = function (f) { return $('[data-f=' + f + ']', r).value; };
      return { name: g('name'), quantity: g('quantity'), unit: g('unit'), unit_other: g('unit_other') };
    });
  }

  /* ---------- submit ---------- */
  function clearErrors() {
    $$('.invalid', form).forEach(function (n) { n.classList.remove('invalid'); });
    $$('.row.has-error', form).forEach(function (n) { n.classList.remove('has-error'); });
    $$('.err', form).forEach(function (n) { n.textContent = ''; });
  }
  function showErrors(fields) {
    var first = null;
    Object.keys(fields).forEach(function (k) {
      var inp = form.elements[k];
      if (k === 'people_count') {
        $('#err-people_count').textContent = fields[k];
        inp = peopleSel.value === 'custom' ? peopleCustom : peopleSel;
      }
      if (k === 'items') $('#err-items').textContent = fields[k];
      if (inp && inp.classList) { inp.classList.add('invalid'); first = first || inp; }
      if (k === 'items') { first = first || $('#err-items'); }
    });
    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function clientValidate(d) {
    var e = {};
    if (d.name.trim().length < 2) e.name = 'Please enter your full name.';
    var dg = d.mobile.replace(/\D/g, '');
    if (dg.length === 12 && dg.indexOf('91') === 0) dg = dg.slice(2);
    else if (dg.length === 11 && dg[0] === '0') dg = dg.slice(1);
    if (!/^[6-9]\d{9}$/.test(dg)) e.mobile = 'Please enter a valid 10-digit mobile number.';
    if (d.address.trim().length < 5) e.address = 'Please enter the event / venue address.';
    if (!d.event_date) e.event_date = 'Please choose the event date.';
    if (!d.event_time) e.event_time = 'Please choose the event timing.';
    if (!d.event_type) e.event_type = 'Please select the event type.';
    return e;
  }

  var submitting = false;
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (submitting) return;
    clearErrors();
    $('#formErr').textContent = '';
    var f = form.elements;
    var data = {
      name: f.name.value, mobile: f.mobile.value, address: f.address.value,
      event_date: f.event_date.value, event_time: f.event_time.value,
      event_type: f.event_type.value, event_type_other: f.event_type_other.value,
      people_count: peopleValue(), items: collectItems(), notes: f.notes.value
    };
    var errs = clientValidate(data);
    if (Object.keys(errs).length) { showErrors(errs); $('#formErr').textContent = 'Please fill in the highlighted fields.'; return; }

    submitting = true;
    var btn = $('#submitBtn'); btn.disabled = true; btn.textContent = 'SUBMITTING…';
    fetch('/api/enquiries', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok) {
          $('#thanksId').textContent = res.j.enquiry_id;
          form.hidden = true; thanks.hidden = false; modal.scrollTop = 0;
        } else {
          if (res.j.fields) showErrors(res.j.fields);
          $('#formErr').textContent = res.j.error || 'Something went wrong. Please try again or call us.';
        }
      })
      .catch(function () { $('#formErr').textContent = 'Network error. Please check your connection and try again.'; })
      .then(function () { submitting = false; btn.disabled = false; btn.textContent = 'SUBMIT ENQUIRY'; });
  });

  function resetForm() {
    form.reset(); clearErrors(); rows.innerHTML = ''; addRow();
    $('#otherTypeWrap').hidden = true; $('#peopleCustomWrap').hidden = true;
    form.hidden = false; thanks.hidden = true;
  }
  addRow();
})();
