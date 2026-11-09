(function () {
    'use strict';
    var root = document.getElementById('fuCalendar');
    if (!root) return;

    var grid = document.getElementById('fuCalGrid');
    var title = document.getElementById('fuCalTitle');
    var detail = document.getElementById('fuCalDetail');
    var patientUrl = root.dataset.patientUrl || '';
    var fRisk = document.getElementById('fuFltRisk');
    var fWhen = document.getElementById('fuFltWhen');
    var fBrgy = document.getElementById('fuFltBrgy');
    var fSearch = document.getElementById('fuFltSearch');
    var fClear = document.getElementById('fuFltClear');
    var fSummary = document.getElementById('fuFltSummary');
    var state = { month: null, today: null, days: {}, selected: null };
    var knownBarangays = {};   
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December'];

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;   
        return n;
    }
    function shortName(p) {
        return (p.last_name || '') + ', ' + ((p.first_name || '').charAt(0) || '') + '.';
    }
    function shiftMonth(ym, delta) {
        var parts = ym.split('-'), d = new Date(+parts[0], +parts[1] - 1 + delta, 1);
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
    }
    function dayState(iso) {
        if (iso < state.today) return 'past';
        if (iso === state.today) return 'today';
        return 'future';
    }

    function matches(p, iso) {
        if (fRisk.value && p.risk !== fRisk.value) return false;
        if (fWhen.value && dayState(iso) !== fWhen.value) return false;
        if (fBrgy.value && (p.barangay || '') !== fBrgy.value) return false;
        var q = fSearch.value.trim().toLowerCase();
        if (q) {
            var hay = ((p.last_name || '') + ' ' + (p.first_name || '') + ' ' + (p.patient_code || '')).toLowerCase();
            if (hay.indexOf(q) === -1) return false;
        }
        return true;
    }
    function dayList(iso) {
        return (state.days[iso] || []).filter(function (p) { return matches(p, iso); });
    }
    function syncBarangays() {
        var grew = false;
        Object.keys(state.days).forEach(function (iso) {
            state.days[iso].forEach(function (p) {
                if (p.barangay && !knownBarangays[p.barangay]) { knownBarangays[p.barangay] = true; grew = true; }
            });
        });
        if (!grew) return;
        var keep = fBrgy.value;
        fBrgy.textContent = '';
        var all = el('option', '', 'All barangays'); all.value = '';
        fBrgy.appendChild(all);
        Object.keys(knownBarangays).sort().forEach(function (b) {
            var o = el('option', '', b); o.value = b; fBrgy.appendChild(o);
        });
        fBrgy.value = keep;
    }
    function updateSummary() {
        var total = 0, shown = 0;
        Object.keys(state.days).forEach(function (iso) {
            total += state.days[iso].length;
            shown += dayList(iso).length;
        });
        var active = fRisk.value || fWhen.value || fBrgy.value || fSearch.value.trim();
        fSummary.textContent = active
            ? 'Showing ' + shown + ' of ' + total + ' follow-ups this month'
            : total + ' follow-up' + (total === 1 ? '' : 's') + ' this month';
    }
    function refresh() {
        render();
        updateSummary();
        if (state.selected) showDetail(state.selected);
    }

    function render() {
        var parts = state.month.split('-'), y = +parts[0], m = +parts[1] - 1;
        title.textContent = MONTHS[m] + ' ' + y;
        grid.textContent = '';
        var startDow = new Date(y, m, 1).getDay();
        var daysInMonth = new Date(y, m + 1, 0).getDate();

        for (var i = 0; i < startDow; i++) grid.appendChild(el('div', 'fu-cell fu-empty'));

        for (var d = 1; d <= daysInMonth; d++) {
            var iso = state.month + '-' + String(d).padStart(2, '0');
            var list = dayList(iso);
            var cell = el('button', 'fu-cell fu-' + dayState(iso) + (list.length ? ' has-pts' : '') +
                          (state.selected === iso ? ' is-selected' : ''));
            cell.type = 'button';
            cell.setAttribute('aria-label', iso + ': ' + list.length + ' patient' + (list.length === 1 ? '' : 's'));
            cell.appendChild(el('span', 'fu-daynum', String(d)));
            if (list.length) {
                cell.appendChild(el('span', 'fu-count', String(list.length)));
                list.slice(0, 2).forEach(function (p) {
                    var row = el('span', 'fu-pt');
                    row.appendChild(el('i', 'fu-dot ' + (p.risk === 'High' ? 'high' : 'mod')));
                    row.appendChild(document.createTextNode(shortName(p)));
                    cell.appendChild(row);
                });
                if (list.length > 2) cell.appendChild(el('span', 'fu-more', '+' + (list.length - 2) + ' more'));
            }
            cell.addEventListener('click', (function (key) {
                return function () { state.selected = key; render(); showDetail(key); };
            })(iso));
            grid.appendChild(cell);
        }
    }

    function showDetail(iso) {
        detail.textContent = '';
        var list = dayList(iso);
        var st = dayState(iso);
        var label = st === 'past' ? 'overdue (no newer visit recorded)' : (st === 'today' ? 'due today' : 'scheduled');
        detail.appendChild(el('h4', 'fu-detail-title', iso + ' \u2014 ' + list.length + ' patient' + (list.length === 1 ? '' : 's') + ' ' + label));
        if (!list.length) {
            detail.appendChild(el('p', 'hr-sub', (state.days[iso] || []).length ? 'No patients on this day match the filters.' : 'No follow-ups on this day.'));
            return;
        }
        var ul = el('ul', 'fu-detail-list');
        list.forEach(function (p) {
            var li = el('li', 'fu-detail-item');
            var a = el('a', 'patient-name-link', (p.last_name || '') + ', ' + (p.first_name || ''));
            a.href = patientUrl.replace('__ID__', encodeURIComponent(p.patient_code));
            li.appendChild(a);
            li.appendChild(el('span', 'risk-badge ' + (p.risk === 'High' ? 'badge-danger' : 'badge-warning'), p.risk || ''));
            var meta = [p.patient_code, p.barangay, p.referred_to || p.referral_action].filter(Boolean).join(' \u00b7 ');
            li.appendChild(el('div', 'hr-sub', meta));
            ul.appendChild(li);
        });
        detail.appendChild(ul);
    }

    function load(ym) {
        fetch('/api/analytics/followup_calendar?month=' + encodeURIComponent(ym || ''), { credentials: 'same-origin' })
            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
            .then(function (data) {
                state.month = data.month; state.today = data.today; state.days = data.days || {};
                if (!state.selected || state.selected.slice(0, 7) !== state.month) {
                    state.selected = (state.today.slice(0, 7) === state.month) ? state.today : null;
                }
                syncBarangays();
                render();
                updateSummary();
                if (state.selected) showDetail(state.selected);
                else { detail.textContent = ''; detail.appendChild(el('p', 'hr-sub', 'Select a day to see its patients.')); }
            })
            .catch(function (err) {
                console.error('Follow-up calendar failed', err);
                grid.textContent = '';
                grid.appendChild(el('p', 'hr-sub', 'Could not load the calendar.'));
            });
    }

    document.getElementById('fuCalPrev').addEventListener('click', function () { load(shiftMonth(state.month, -1)); });
    document.getElementById('fuCalNext').addEventListener('click', function () { load(shiftMonth(state.month, 1)); });
    document.getElementById('fuCalToday').addEventListener('click', function () { state.selected = null; load(''); });

    [fRisk, fWhen, fBrgy].forEach(function (n) { n.addEventListener('change', refresh); });
    fSearch.addEventListener('input', refresh);
    fClear.addEventListener('click', function () {
        fRisk.value = ''; fWhen.value = ''; fBrgy.value = ''; fSearch.value = '';
        refresh();
    });

    load('');
})();