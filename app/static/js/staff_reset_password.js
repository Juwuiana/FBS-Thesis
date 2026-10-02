(() => {
  const resetButton = document.querySelector('.reset-password-btn');
  const modalElement = document.getElementById('resetPasswordModal');
  const recipient = document.getElementById('resetPasswordRecipient');
  const password = document.getElementById('resetPasswordValue');
  const statusPill = document.getElementById('staffStatusPill');
  const copyButton = document.getElementById('copyResetPassword');

  if (!resetButton || !modalElement || !recipient || !password || !statusPill || !copyButton) return;

  resetButton.addEventListener('click', async () => {
    if (!window.confirm('Reset this employee password and issue a temporary password?')) return;
    resetButton.disabled = true;
    try {
      const response = await fetch(resetButton.dataset.resetUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'The password reset could not be completed.');
      recipient.textContent = `${payload.name} · ${payload.email}`;
      password.value = payload.temp_password;
      statusPill.className = 'risk-pill risk-low';
      statusPill.textContent = 'Approved';
      bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } catch (error) {
      window.alert(error.message);
    } finally {
      resetButton.disabled = false;
    }
  });

  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(password.value);
      copyButton.innerHTML = '<i class="bi bi-check2 me-1"></i> Copied';
    } catch (error) {
      password.select();
      document.execCommand('copy');
      copyButton.innerHTML = '<i class="bi bi-check2 me-1"></i> Copied';
    }
  });
})();
