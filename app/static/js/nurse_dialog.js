// static/js/nurse_dialog.js
// Shared popup dialogs for the nurse pages. Replaces the browser's native
// alert()/confirm() boxes with a white card that has an X at the top right
// and an OK button.
//
//   nurseAlert(message, { title })            -> Promise (resolves when closed)
//   nurseConfirm(message, { title, okText })  -> Promise<boolean>
//
// window.alert is routed through nurseAlert, so existing alert('...') calls
// pick up the new look with no changes. NOTE: it is no longer blocking --
// if code must wait for the nurse to dismiss it (e.g. before a redirect),
// use `await nurseAlert(...)` instead.
//
// Forms can ask for a confirmation with data-confirm="Are you sure?" in place
// of onsubmit="return confirm(...)" -- handled at the bottom of this file.
(function () {
    if (window.nurseAlert) return;

    let queue = Promise.resolve();   // dialogs show one at a time, in order

    function show({ title, message, okText, cancelText }) {
        return new Promise((resolve) => {
            const prevFocus = document.activeElement;
            const isConfirm = !!cancelText;

            const overlay = document.createElement('div');
            overlay.className = 'nurse-modal-overlay';

            const modal = document.createElement('div');
            modal.className = 'nurse-modal nurse-dialog';
            modal.setAttribute('role', isConfirm ? 'dialog' : 'alertdialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', 'nurseDialogTitle');
            modal.setAttribute('aria-describedby', 'nurseDialogMsg');

            const head = document.createElement('div');
            head.className = 'nurse-dialog-head';
            const h3 = document.createElement('h3');
            h3.id = 'nurseDialogTitle';
            h3.textContent = title;
            const x = document.createElement('button');
            x.type = 'button';
            x.className = 'nurse-dialog-x';
            x.setAttribute('aria-label', 'Close');
            x.innerHTML = '&times;';
            head.append(h3, x);

            const p = document.createElement('p');
            p.id = 'nurseDialogMsg';
            p.className = 'nurse-dialog-msg';
            p.textContent = message;          // textContent: server error text can't inject HTML

            const actions = document.createElement('div');
            actions.className = 'nurse-modal-actions';
            let cancelBtn = null;
            if (isConfirm) {
                cancelBtn = document.createElement('button');
                cancelBtn.type = 'button';
                cancelBtn.className = 'btn btn-secondary';
                cancelBtn.textContent = cancelText;
                actions.appendChild(cancelBtn);
            }
            const okBtn = document.createElement('button');
            okBtn.type = 'button';
            okBtn.className = 'btn btn-primary';
            okBtn.textContent = okText;
            actions.appendChild(okBtn);

            modal.append(head, p, actions);
            overlay.appendChild(modal);
            document.body.appendChild(overlay);
            okBtn.focus();

            function close(result) {
                document.removeEventListener('keydown', onKey, true);
                overlay.remove();
                if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
                resolve(result);
            }
            function onKey(ev) {
                if (ev.key === 'Escape') { ev.preventDefault(); close(false); return; }
                if (ev.key === 'Tab') {            // keep focus inside the dialog
                    const items = modal.querySelectorAll('button');
                    const first = items[0], last = items[items.length - 1];
                    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
                    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
                }
            }
            document.addEventListener('keydown', onKey, true);
            okBtn.addEventListener('click', () => close(true));
            x.addEventListener('click', () => close(false));
            if (cancelBtn) cancelBtn.addEventListener('click', () => close(false));
            overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
        });
    }

    function enqueue(opts) {
        const result = queue.then(() => show(opts));
        queue = result.catch(() => {});
        return result;
    }

    window.nurseAlert = (message, opts = {}) =>
        enqueue({ title: opts.title || 'Notice', message: String(message ?? ''), okText: opts.okText || 'OK' });

    window.nurseConfirm = (message, opts = {}) =>
        enqueue({ title: opts.title || 'Please confirm', message: String(message ?? ''),
                  okText: opts.okText || 'OK', cancelText: opts.cancelText || 'Cancel' });

    window.alert = (message) => { window.nurseAlert(message); };

    // <form data-confirm="..."> asks first, then submits for real on OK.
    document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;
        e.preventDefault();
        window.nurseConfirm(form.dataset.confirm).then((ok) => {
            // prototype call: still works if a form has a control named "submit"
            if (ok) HTMLFormElement.prototype.submit.call(form);
        });
    });
})();
