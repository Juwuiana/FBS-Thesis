document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('csvImportForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('csvImportFile');
        const resultDiv = document.getElementById('csvImportResult');
        if (!fileInput.files.length) return;

        const formData = new FormData();
        formData.append('csv_import', fileInput.files[0]);

        resultDiv.textContent = 'Uploading...';
        resultDiv.style.color = 'var(--text-muted)';

        try {
            const res = await fetch(window.__csvImportUrl, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (!res.ok) {
                resultDiv.textContent = data.error || 'Import failed.';
                resultDiv.style.color = 'var(--danger)';
                return;
            }

            resultDiv.style.color = data.skipped > 0 ? '#b45309' : 'var(--green-accent)';
            resultDiv.innerHTML = `${data.message}` +
                (data.errors.length ? `<br><ul style="margin-top:0.4rem; padding-left:1.1rem;">${data.errors.map(e => `<li>${e}</li>`).join('')}</ul>` : '');

            if (data.created > 0) {
                setTimeout(() => window.location.reload(), 2500);
            }
        } catch (err) {
            resultDiv.textContent = 'Network error during import.';
            resultDiv.style.color = 'var(--danger)';
        }
    });
});