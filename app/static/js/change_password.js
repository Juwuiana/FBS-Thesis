/* Shared Change Password behaviour (admin + nurse). Guidance only: the server enforces the rules.
   Keep the rule checks below in sync with PASSWORD_REGEX in app/controllers/auth_controller.py.
   ("must not contain your name or email" is checked on the server only.) */
(function () {
    function init(form) {
        var minLen = parseInt(form.dataset.cpMin, 10) || 12;
        var cur = form.querySelector('input[name="current_password"]');
        var nw = form.querySelector('input[name="new_password"]');
        var conf = form.querySelector('input[name="confirm_password"]');
        var submit = form.querySelector('[data-cp-submit]');
        var fill = form.querySelector('[data-cp-strength-fill]');
        var label = form.querySelector('[data-cp-strength-label]');
        var match = form.querySelector('[data-cp-match]');
        var levels = [
            { text: 'Weak', color: 'var(--danger)', pct: 25 },
            { text: 'Fair', color: '#f0a500', pct: 50 },
            { text: 'Good', color: '#8bc34a', pct: 75 },
            { text: 'Strong', color: 'var(--g-accent)', pct: 100 }
        ];

        function score(pw) {
            if (!pw) return -1;
            var pts = 0;
            if (pw.length >= 8) pts++;
            if (pw.length >= minLen) pts++;
            if (pw.length >= 16) pts++;
            var kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(function (r) { return r.test(pw); }).length;
            pts += kinds - 1;
            var lvl = pts <= 2 ? 0 : pts === 3 ? 1 : pts === 4 ? 2 : 3;
            return pw.length < minLen ? Math.min(lvl, 1) : lvl;
        }

        function setRule(name, ok) {
            var li = form.querySelector('[data-cp-rule="' + name + '"]');
            if (!li) return;
            li.classList.toggle('is-met', ok);
            var st = li.querySelector('.cp-rule-state');
            if (st) st.textContent = ok ? 'Met' : 'Not met';
        }

        function update() {
            var pw = nw.value, cf = conf.value, cu = cur.value;
            var s = score(pw);
            if (s < 0) {
                fill.style.width = '0'; label.textContent = ''; label.style.color = '';
            } else {
                var lv = levels[s];
                fill.style.width = lv.pct + '%'; fill.style.background = lv.color;
                label.textContent = 'Strength: ' + lv.text; label.style.color = lv.color;
            }

            var okLen = pw.length >= minLen;
            var okUpper = /[A-Z]/.test(pw);
            var okLower = /[a-z]/.test(pw);
            var okNumber = /[0-9]/.test(pw);
            var okSpecial = /[^A-Za-z0-9\s]/.test(pw);
            var okRepeat = pw.length > 0 && !/\s/.test(pw) && !/(.)\1\1/s.test(pw);
            var okPolicy = okLen && okUpper && okLower && okNumber && okSpecial && okRepeat;
            var okMatch = pw.length > 0 && pw === cf;
            var okDiff = pw.length > 0 && cu.length > 0 && pw !== cu;
            setRule('length', okLen);
            setRule('upper', okUpper);
            setRule('lower', okLower);
            setRule('number', okNumber);
            setRule('special', okSpecial);
            setRule('repeat', okRepeat);
            setRule('match', okMatch);
            setRule('different', okDiff);

            if (!cf) {
                match.textContent = ''; match.className = 'form-hint cp-match';
            } else if (okMatch) {
                match.textContent = '\u2713 Passwords match'; match.className = 'form-hint cp-match cp-ok';
            } else {
                match.textContent = '\u2717 Passwords do not match'; match.className = 'form-hint cp-match cp-bad';
            }
            submit.disabled = !(okPolicy && okMatch && okDiff) || form.dataset.submitting === '1';
        }

        [cur, nw, conf].forEach(function (el) { el.addEventListener('input', update); });

        form.querySelectorAll('[data-pw-toggle]').forEach(function (btn) {
            var input = document.getElementById(btn.dataset.pwToggle);
            if (!input) return;
            btn.addEventListener('click', function () {
                var show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                var text = show ? 'Hide password' : 'Show password';
                btn.setAttribute('aria-pressed', show ? 'true' : 'false');
                btn.setAttribute('aria-label', text);
                btn.title = text;
                btn.querySelector('.eye-open').style.display = show ? 'none' : '';
                btn.querySelector('.eye-off').style.display = show ? '' : 'none';
            });
        });

        form.querySelector('[data-cp-clear]').addEventListener('click', function () {
            form.reset();
            form.querySelectorAll('[data-pw-toggle]').forEach(function (btn) {
                var input = document.getElementById(btn.dataset.pwToggle);
                if (input && input.type === 'text') btn.click();
            });
            update();
            cur.focus();
        });

        form.addEventListener('submit', function (e) {
            if (submit.disabled) { e.preventDefault(); return; }
            form.dataset.submitting = '1';
            submit.disabled = true;
            submit.textContent = 'Updating\u2026';
        });

        window.addEventListener('pageshow', function () {
            form.dataset.submitting = '';
            submit.textContent = 'Update Password';
            update();
        });
        update();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-cp-form]').forEach(init);
    });
})();
